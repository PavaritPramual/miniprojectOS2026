#!/bin/sh
# Creates the same demo folder as tools/prepare_demo_fixture.ps1, from Ubuntu/WSL.
#
#   sh tools/make_demo_fixture.sh <new-folder> [--with-issues]
#
# Plain demo: 64 files, 13 directories including the root.
# --with-issues adds cases the scanner must report instead of hiding:
#   back-to-root    symlink to the root itself (would loop forever if followed)
#   broken-link     symlink to nothing
#   pipe.fifo       a FIFO (not a regular file)
#   no-access/      directory with mode 000 (EACCES unless you are root)
#   back\slash.txt  name with a backslash (cannot be represented in the contract)
#   bad-<0xFF>-name.txt  name that is not valid UTF-8
set -eu

target=${1:-}
if [ -z "$target" ]; then
    echo "usage: sh $0 <new-folder> [--with-issues]" >&2
    exit 2
fi
if [ -e "$target" ]; then
    echo "Target already exists; refusing to overwrite: $target" >&2
    exit 1
fi
with_issues=0
[ "${2:-}" = "--with-issues" ] && with_issues=1

mkdir -p "$target/empty" "$target/many" "$target/ชื่อ ไทย"

cursor="$target/depth"
mkdir "$cursor"
level=1
while [ "$level" -le 8 ]; do
    cursor="$cursor/level-$(printf '%02d' "$level")"
    mkdir "$cursor"
    level=$((level + 1))
done
printf 'deep' > "$cursor/leaf.txt"

number=1
while [ "$number" -le 60 ]; do
    printf 'x' > "$target/many/child-$(printf '%03d' "$number").txt"
    number=$((number + 1))
done

printf 'hello' > "$target/ชื่อ ไทย/รายงาน 1.txt"
: > "$target/zero.bin"
head -c 1048576 /dev/zero > "$target/large.bin"

if [ "$with_issues" -eq 1 ]; then
    ln -s "$target" "$target/back-to-root"
    ln -s does-not-exist "$target/broken-link"
    mkfifo "$target/pipe.fifo"
    mkdir "$target/no-access"
    printf 'secret' > "$target/no-access/hidden.txt"
    chmod 000 "$target/no-access"
    printf 'x' > "$target/back\\slash.txt"
    bad=$(printf 'bad-\377-name.txt')
    printf 'x' > "$target/$bad"
fi

echo "Created: $target"
find "$target" -type f 2>/dev/null | wc -l | sed 's/^ *//; s/$/ regular files/'
