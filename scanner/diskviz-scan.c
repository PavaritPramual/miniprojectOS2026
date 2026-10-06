/*
 * diskviz-scan - CoreSpace C scanner (part C, see docs/CONTRACT.md section 1)
 *
 *   diskviz-scan --root <absolute-path> --ndjson
 *
 * Walks <root> and prints one UTF-8 JSON record per line on stdout:
 *
 *   entry    one per file / directory / link. The root comes first and a
 *            directory is always printed before anything inside it.
 *   error    an item could not be read. No size is invented for it.
 *   skipped  an item was deliberately not followed (symlink, loop, special file).
 *   done     always the last record: counts and "complete".
 *
 * Diagnostics go to stderr, never stdout.
 *
 * Exit codes: 0 complete, 1 partial (errors or skipped items), 2 bad input,
 *             3 internal error (out of memory), 130 cancelled by a signal.
 *
 * Only POSIX calls are used: opendir/readdir, lstat, sigaction, write via stdio.
 */
#define _POSIX_C_SOURCE 200809L
#define _FILE_OFFSET_BITS 64

#include <dirent.h>
#include <errno.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <time.h>
#include <unistd.h>

#define PROGRAM "diskviz-scan"

#define EXIT_COMPLETE 0
#define EXIT_PARTIAL 1
#define EXIT_USAGE 2
#define EXIT_INTERNAL 3
#define EXIT_CANCELLED 130

/* The Python side saves every 128 records or 1 s; we flush a little earlier. */
#define FLUSH_EVERY_RECORDS 128
#define FLUSH_EVERY_MS 250
#define FLUSH_BEFORE_SLOW_CALL_MS 100

/* ---------- growable string ---------- */

typedef struct {
    char *p;
    size_t len;
    size_t cap;
} Buf;

static void die_oom(void)
{
    static const char msg[] = PROGRAM ": out of memory\n";
    if (write(STDERR_FILENO, msg, sizeof msg - 1) < 0) { /* nothing more to do */ }
    _exit(EXIT_INTERNAL);
}

static void buf_append(Buf *b, const char *s, size_t n)
{
    if (b->len + n + 1 > b->cap) {
        size_t cap = b->cap ? b->cap : 256;
        while (cap < b->len + n + 1)
            cap *= 2;
        char *p = realloc(b->p, cap);
        if (!p)
            die_oom();
        b->p = p;
        b->cap = cap;
    }
    if (n)
        memcpy(b->p + b->len, s, n);
    b->len += n;
    b->p[b->len] = '\0';
}

static void buf_truncate(Buf *b, size_t len)
{
    b->len = len;
    b->p[len] = '\0';
}

/* ---------- scan state ---------- */

typedef struct {
    dev_t dev;
    ino_t ino;
} FileId;

static struct {
    Buf abs;                 /* absolute path of the directory/entry being handled */
    Buf rel;                 /* the same path relative to root, '/' separated, "" = root */
    unsigned long long files, dirs, errors, skipped;
    FileId *anc;             /* directories on the current path, used to detect loops */
    size_t anc_len, anc_cap;
    unsigned pending;        /* records written since the last flush */
    int out_failed;          /* stdout could not be written (reader went away) */
} S;

static long long g_last_flush_ms;

static long long mono_ms(void)
{
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return (long long)t.tv_sec * 1000 + t.tv_nsec / 1000000;
}

/* ---------- cancellation ---------- */

/*
 * A signal ends the program at once. The consumer cancels by sending SIGTERM,
 * and we may be blocked writing to a full pipe, so a flag checked "later"
 * would not be reliable. _exit() is async-signal-safe. No "done" record is
 * written: a stream without "done" is how the consumer knows it is incomplete.
 */
static void on_signal(int sig)
{
    (void)sig;
    _exit(EXIT_CANCELLED);
}

static void install_signal_handlers(void)
{
    struct sigaction sa;
    memset(&sa, 0, sizeof sa);
    sa.sa_handler = on_signal;
    sigemptyset(&sa.sa_mask);
    sigaction(SIGINT, &sa, NULL);
    sigaction(SIGTERM, &sa, NULL);
    sigaction(SIGHUP, &sa, NULL);

    /* A closed pipe should show up as a write error, not kill us silently. */
    signal(SIGPIPE, SIG_IGN);
}

/* ---------- output ---------- */

static void flush_out(void)
{
    if (fflush(stdout) != 0)
        S.out_failed = 1;
    S.pending = 0;
    g_last_flush_ms = mono_ms();
}

static void record_written(void)
{
    if (ferror(stdout))
        S.out_failed = 1;
    if (++S.pending >= FLUSH_EVERY_RECORDS || mono_ms() - g_last_flush_ms >= FLUSH_EVERY_MS)
        flush_out();
}

/* Called before a call that may block for a while, so the reader sees what we have. */
static void flush_if_idle(void)
{
    if (S.pending && mono_ms() - g_last_flush_ms >= FLUSH_BEFORE_SLOW_CALL_MS)
        flush_out();
}

static void check_output(void)
{
    if (S.out_failed) {
        fputs(PROGRAM ": cannot write to stdout (reader closed?); stopping\n", stderr);
        _exit(EXIT_PARTIAL);
    }
}

/* Length of the valid UTF-8 sequence at s (lead byte >= 0x80), or 0 if invalid. */
static size_t utf8_seq_len(const unsigned char *s, size_t n)
{
    unsigned char c = s[0];
    size_t len;
    uint32_t cp, min;

    if (c >= 0xC2 && c <= 0xDF) {
        len = 2; cp = c & 0x1F; min = 0x80;
    } else if (c >= 0xE0 && c <= 0xEF) {
        len = 3; cp = c & 0x0F; min = 0x800;
    } else if (c >= 0xF0 && c <= 0xF4) {
        len = 4; cp = c & 0x07; min = 0x10000;
    } else {
        return 0;
    }
    if (n < len)
        return 0;
    for (size_t k = 1; k < len; k++) {
        if ((s[k] & 0xC0) != 0x80)
            return 0;
        cp = (cp << 6) | (s[k] & 0x3F);
    }
    if (cp < min || cp > 0x10FFFF || (cp >= 0xD800 && cp <= 0xDFFF))
        return 0;
    return len;
}

static int utf8_valid(const char *s)
{
    const unsigned char *u = (const unsigned char *)s;
    while (*u) {
        if (*u < 0x80) {
            u++;
        } else {
            size_t len = utf8_seq_len(u, strlen((const char *)u));
            if (!len)
                return 0;
            u += len;
        }
    }
    return 1;
}

/* Writes s as a JSON string. Invalid UTF-8 bytes become U+FFFD so the line stays valid JSON. */
static void put_json_string(const char *s, size_t n)
{
    static const char hex[] = "0123456789abcdef";
    size_t i = 0;

    putc_unlocked('"', stdout);
    while (i < n) {
        unsigned char c = (unsigned char)s[i];
        if (c < 0x80) {
            switch (c) {
            case '"':  fputs("\\\"", stdout); break;
            case '\\': fputs("\\\\", stdout); break;
            case '\n': fputs("\\n", stdout); break;
            case '\r': fputs("\\r", stdout); break;
            case '\t': fputs("\\t", stdout); break;
            case '\b': fputs("\\b", stdout); break;
            case '\f': fputs("\\f", stdout); break;
            default:
                if (c < 0x20) {
                    fputs("\\u00", stdout);
                    putc_unlocked(hex[c >> 4], stdout);
                    putc_unlocked(hex[c & 15], stdout);
                } else {
                    putc_unlocked(c, stdout);
                }
            }
            i++;
        } else {
            size_t len = utf8_seq_len((const unsigned char *)s + i, n - i);
            if (len) {
                fwrite(s + i, 1, len, stdout);
                i += len;
            } else {
                fputs("\xEF\xBF\xBD", stdout);
                i++;
            }
        }
    }
    putc_unlocked('"', stdout);
}

static void put_cstr(const char *s)
{
    put_json_string(s, strlen(s));
}

static void emit_root(const char *name)
{
    fputs("{\"type\":\"entry\",\"relativePath\":\"\",\"parentRelativePath\":null,\"name\":", stdout);
    put_cstr(name);
    fputs(",\"kind\":\"directory\",\"logicalBytes\":0}\n", stdout);
    record_written();
}

/* S.rel already holds the full relative path of the item; its first parent_len bytes are the parent. */
static void emit_entry(const char *name, size_t parent_len, const char *kind, long long bytes)
{
    fputs("{\"type\":\"entry\",\"relativePath\":", stdout);
    put_json_string(S.rel.p, S.rel.len);
    fputs(",\"parentRelativePath\":", stdout);
    put_json_string(S.rel.p, parent_len);
    fputs(",\"name\":", stdout);
    put_cstr(name);
    fprintf(stdout, ",\"kind\":\"%s\",\"logicalBytes\":%lld}\n", kind, bytes);
    record_written();
}

static void emit_skipped(const char *reason)
{
    fputs("{\"type\":\"skipped\",\"relativePath\":", stdout);
    put_json_string(S.rel.p, S.rel.len);
    fputs(",\"reason\":", stdout);
    put_cstr(reason);
    fputs("}\n", stdout);
    S.skipped++;
    record_written();
}

static void emit_error_text(const char *code, const char *message)
{
    fputs("{\"type\":\"error\",\"relativePath\":", stdout);
    put_json_string(S.rel.p, S.rel.len);
    fputs(",\"code\":", stdout);
    put_cstr(code);
    fputs(",\"message\":", stdout);
    put_cstr(message);
    fputs("}\n", stdout);
    S.errors++;
    record_written();
}

static const char *errno_code(int e, char *fallback, size_t n)
{
    switch (e) {
    case EACCES:       return "EACCES";
    case EPERM:        return "EPERM";
    case ENOENT:       return "ENOENT";
    case ENOTDIR:      return "ENOTDIR";
    case ELOOP:        return "ELOOP";
    case ENAMETOOLONG: return "ENAMETOOLONG";
    case EIO:          return "EIO";
    case EMFILE:       return "EMFILE";
    case ENFILE:       return "ENFILE";
    case ENOMEM:       return "ENOMEM";
    case EOVERFLOW:    return "EOVERFLOW";
    case ESTALE:       return "ESTALE";
    case EBUSY:        return "EBUSY";
    case ENXIO:        return "ENXIO";
    case ENODEV:       return "ENODEV";
    default:
        snprintf(fallback, n, "ERRNO_%d", e);
        return fallback;
    }
}

static void emit_errno(const char *operation, int err)
{
    char fallback[24];
    char msg[320];
    snprintf(msg, sizeof msg, "%s: %s", operation, strerror(err));
    emit_error_text(errno_code(err, fallback, sizeof fallback), msg);
}

/* ---------- directory walk ---------- */

typedef struct {
    char **v;
    size_t n, cap;
} NameList;

static void names_add(NameList *l, const char *name)
{
    if (l->n == l->cap) {
        size_t cap = l->cap ? l->cap * 2 : 64;
        char **v = realloc(l->v, cap * sizeof *v);
        if (!v)
            die_oom();
        l->v = v;
        l->cap = cap;
    }
    l->v[l->n] = strdup(name);
    if (!l->v[l->n])
        die_oom();
    l->n++;
}

static void names_free(NameList *l)
{
    for (size_t i = 0; i < l->n; i++)
        free(l->v[i]);
    free(l->v);
}

static int cmp_names(const void *a, const void *b)
{
    return strcmp(*(char *const *)a, *(char *const *)b);
}

static void anc_push(dev_t dev, ino_t ino)
{
    if (S.anc_len == S.anc_cap) {
        size_t cap = S.anc_cap ? S.anc_cap * 2 : 32;
        FileId *p = realloc(S.anc, cap * sizeof *p);
        if (!p)
            die_oom();
        S.anc = p;
        S.anc_cap = cap;
    }
    S.anc[S.anc_len].dev = dev;
    S.anc[S.anc_len].ino = ino;
    S.anc_len++;
}

/* True if this directory is already on the path we came down: following it would loop. */
static int anc_contains(const struct stat *st)
{
    if (st->st_ino == 0) /* filesystem gives no usable inode number */
        return 0;
    for (size_t i = 0; i < S.anc_len; i++)
        if (S.anc[i].dev == st->st_dev && S.anc[i].ino == st->st_ino)
            return 1;
    return 0;
}

/* A name we can report faithfully: valid UTF-8 and no backslash (the contract uses '/' only). */
static int name_supported(const char *name)
{
    return name[0] != '\0' && strchr(name, '\\') == NULL && utf8_valid(name);
}

static void walk_dir(void);

static void handle_child(const char *name, size_t parent_len)
{
    struct stat st;

    if (!name_supported(name)) {
        emit_error_text("UNSUPPORTED_NAME",
                        "name is not valid UTF-8 or contains a backslash; it cannot be reported safely");
        return;
    }
    if (lstat(S.abs.p, &st) != 0) {
        emit_errno("lstat", errno);
        return;
    }

    if (S_ISREG(st.st_mode)) {
        if (st.st_size < 0) {
            emit_error_text("EOVERFLOW", "lstat: negative file size");
            return;
        }
        emit_entry(name, parent_len, "file", (long long)st.st_size);
        S.files++;
    } else if (S_ISDIR(st.st_mode)) {
        if (anc_contains(&st)) {
            emit_entry(name, parent_len, "link", 0);
            emit_skipped("directory_loop");
        } else {
            emit_entry(name, parent_len, "directory", 0);
            S.dirs++;
            anc_push(st.st_dev, st.st_ino);
            walk_dir();
            S.anc_len--;
        }
    } else if (S_ISLNK(st.st_mode)) {
        emit_entry(name, parent_len, "link", 0);
        emit_skipped("symlink");
    } else {
        /* fifo, socket, device: the contract has no kind for them */
        emit_skipped("special_file");
    }
}

/* Lists the directory named by S.abs/S.rel and handles each child, sorted by name. */
static void walk_dir(void)
{
    NameList names = {0};
    struct dirent *e;
    int read_err;
    size_t seen = 0;
    DIR *d;

    check_output();
    flush_if_idle();

    d = opendir(S.abs.p);
    if (!d) {
        emit_errno("opendir", errno);
        return;
    }
    for (;;) {
        errno = 0;
        e = readdir(d);
        if (!e)
            break;
        if (e->d_name[0] == '.' &&
            (e->d_name[1] == '\0' || (e->d_name[1] == '.' && e->d_name[2] == '\0')))
            continue;
        names_add(&names, e->d_name);
        if ((++seen & 1023) == 0)
            check_output();
    }
    read_err = errno;
    closedir(d); /* no descriptor stays open while we go deeper */

    if (read_err)
        emit_errno("readdir", read_err);

    if (names.n > 1) /* qsort(NULL, 0, ...) is undefined, so skip empty directories */
        qsort(names.v, names.n, sizeof *names.v, cmp_names); /* same output on every run */

    for (size_t i = 0; i < names.n; i++) {
        size_t abs_mark = S.abs.len;
        size_t rel_mark = S.rel.len;

        check_output();
        buf_append(&S.abs, "/", 1);
        buf_append(&S.abs, names.v[i], strlen(names.v[i]));
        if (rel_mark)
            buf_append(&S.rel, "/", 1);
        buf_append(&S.rel, names.v[i], strlen(names.v[i]));

        handle_child(names.v[i], rel_mark);

        buf_truncate(&S.abs, abs_mark);
        buf_truncate(&S.rel, rel_mark);
    }
    names_free(&names);
}

/* ---------- command line ---------- */

static void print_usage(FILE *f)
{
    fputs("usage: " PROGRAM " --root <absolute-path> --ndjson\n"
          "\n"
          "Scans <absolute-path> and prints NDJSON records on stdout (see docs/CONTRACT.md).\n"
          "exit: 0 complete, 1 partial, 2 bad input, 3 internal error, 130 cancelled\n",
          f);
}

static void usage_error(const char *what, const char *detail)
{
    fprintf(stderr, PROGRAM ": %s%s%s\n", what, detail ? ": " : "", detail ? detail : "");
    print_usage(stderr);
    exit(EXIT_USAGE);
}

/* Validates --root; leaves the normalised path (no trailing '/') in out and returns the root's name. */
static const char *prepare_root(const char *arg, Buf *out)
{
    struct stat st;
    const char *start, *p, *slash;

    if (arg[0] != '/')
        usage_error("--root must be an absolute path", arg);

    buf_append(out, arg, strlen(arg));
    while (out->len > 0 && out->p[out->len - 1] == '/')
        buf_truncate(out, out->len - 1);
    if (out->len == 0)
        usage_error("refusing to scan the filesystem root '/'", NULL);

    for (start = out->p; *start;) {
        size_t n;
        while (*start == '/')
            start++;
        for (p = start; *p && *p != '/'; p++)
            ;
        n = (size_t)(p - start);
        if ((n == 1 && start[0] == '.') || (n == 2 && start[0] == '.' && start[1] == '.'))
            usage_error("--root must not contain '.' or '..' components", arg);
        start = p;
    }

    if (stat(out->p, &st) != 0) {
        fprintf(stderr, PROGRAM ": cannot access root %s: %s\n", out->p, strerror(errno));
        exit(EXIT_USAGE);
    }
    if (!S_ISDIR(st.st_mode)) {
        fprintf(stderr, PROGRAM ": root is not a directory: %s\n", out->p);
        exit(EXIT_USAGE);
    }

    slash = strrchr(out->p, '/');
    if (!name_supported(slash + 1)) {
        fprintf(stderr, PROGRAM ": root name is not valid UTF-8 or contains a backslash: %s\n", out->p);
        exit(EXIT_USAGE);
    }
    anc_push(st.st_dev, st.st_ino);
    return slash + 1;
}

int main(int argc, char **argv)
{
    const char *root_arg = NULL;
    const char *root_name;
    int ndjson = 0;
    int complete;
    Buf root = {0};

    for (int i = 1; i < argc; i++) {
        const char *a = argv[i];
        if (strcmp(a, "--help") == 0 || strcmp(a, "-h") == 0) {
            print_usage(stdout);
            return EXIT_COMPLETE;
        } else if (strcmp(a, "--ndjson") == 0) {
            ndjson = 1;
        } else if (strcmp(a, "--root") == 0) {
            if (i + 1 >= argc)
                usage_error("--root needs a value", NULL);
            if (root_arg)
                usage_error("--root given more than once", NULL);
            root_arg = argv[++i];
        } else if (strncmp(a, "--root=", 7) == 0) {
            if (root_arg)
                usage_error("--root given more than once", NULL);
            root_arg = a + 7;
        } else {
            usage_error("unknown argument", a);
        }
    }
    if (!root_arg)
        usage_error("--root is required", NULL);
    if (!ndjson)
        usage_error("--ndjson is required (the only output format)", NULL);

    root_name = prepare_root(root_arg, &root);

    install_signal_handlers();
    setvbuf(stdout, NULL, _IOFBF, 1 << 16);
    g_last_flush_ms = mono_ms();

    buf_append(&S.abs, root.p, root.len);
    buf_append(&S.rel, "", 0);

    emit_root(root_name);
    S.dirs = 1; /* directoryCount includes the root */
    flush_out(); /* the consumer saves the root straight away */

    walk_dir();

    complete = (S.errors == 0 && S.skipped == 0);
    fprintf(stdout,
            "{\"type\":\"done\",\"fileCount\":%llu,\"directoryCount\":%llu,"
            "\"errorCount\":%llu,\"skippedCount\":%llu,\"complete\":%s}\n",
            S.files, S.dirs, S.errors, S.skipped, complete ? "true" : "false");
    flush_out();
    check_output();

    if (!complete)
        fprintf(stderr, PROGRAM ": partial result: %llu error(s), %llu skipped item(s)\n",
                S.errors, S.skipped);

    free(root.p);
    free(S.abs.p);
    free(S.rel.p);
    free(S.anc);
    return complete ? EXIT_COMPLETE : EXIT_PARTIAL;
}
