/* File-city layout. Folder area is never added to its file area twice.
   Research and mapping decisions: docs/FILE_CITY.md. */
((root) => {
  const library = typeof module !== 'undefined' && module.exports ? require('./vendor/d3-hierarchy-3.1.2.min.js') : root.d3;
  const valid = value => Number.isSafeInteger(value) && value >= 0;
  const categories = {
    directory: {label:'โฟลเดอร์',color:'#39796b'},
    video: {label:'วิดีโอ',color:'#cf7650'},
    image: {label:'รูปภาพ',color:'#d0a338'},
    audio: {label:'เสียง',color:'#9873a7'},
    archive: {label:'ไฟล์บีบอัด',color:'#7d85ab'},
    document: {label:'เอกสาร',color:'#5188af'},
    other: {label:'ไฟล์อื่น',color:'#7b8b96'},
    reserve: {label:'ยังไม่แสดงรายละเอียด',color:'#bbc6c9'},
  };
  function category(item) {
    if (item.kind === 'directory') return 'directory';
    const ext=item.name.split('.').pop().toLowerCase();
    if (['mp4','mkv','mov','avi','webm'].includes(ext)) return 'video';
    if (['png','jpg','jpeg','gif','webp','svg','heic'].includes(ext)) return 'image';
    if (['mp3','wav','flac','aac','ogg'].includes(ext)) return 'audio';
    if (['zip','rar','7z','tar','gz'].includes(ext)) return 'archive';
    if (['txt','pdf','doc','docx','ppt','pptx','xls','xlsx','md','csv'].includes(ext)) return 'document';
    return 'other';
  }
  function buildCity(items, pages, metric='allocatedBytes', folder={name:'โฟลเดอร์ที่เลือก',relativePath:'',kind:'directory'}) {
    const unplaced=[], records=[], districts=[];
    let count=0;
    function collect(items,depth,owner) {
      const output=[],reserves=[];
      for(const item of items){const node=branch(item,depth,owner);if(node?.kind==='reserve')reserves.push(node);else if(node)output.push(node);}
      if(reserves.length)output.push({name:`รายการรวม ${reserves.length} รายการ`,kind:'reserve',weight:reserves.reduce((n,x)=>n+x.bytes,0),bytes:reserves.reduce((n,x)=>n+x.bytes,0),owner});
      return output;
    }
    function branch(item, depth, owner) {
      const bytes=item[metric];
      if(!valid(bytes)||bytes===0){unplaced.push(item);return null;}
      if(count>=250) return {name:'รายการรวม',kind:'reserve',weight:bytes,bytes,owner};
      count++;
      const data={item,name:item.name,kind:item.kind,bytes,category:category(item),weight:bytes};
      const page=pages[item.relativePath];
      if(item.kind==='directory' && depth<2 && page?.loaded && page.items.length){
        const candidates=collect(page.items,depth+1,item);
        const sum=candidates.reduce((total,child)=>total+child.bytes,0);
        // Live folder totals can lag incoming entries. Keep the folder opaque until consistent.
        if(sum<=bytes){
          data.weight=0;data.children=candidates;
          if(bytes>sum)data.children.push({name:'ยังไม่แสดงรายละเอียด',kind:'reserve',weight:bytes-sum,bytes:bytes-sum,owner:item});
        }
      }
      return data;
    }
    const children=collect(items,0,folder);
    const tree=library.hierarchy({name:'root',children}).sum(data=>data.weight||0).sort((a,b)=>b.value-a.value||a.data.name.localeCompare(b.data.name));
    library.treemap().size([700,440]).paddingInner(5).paddingOuter(7).paddingTop(node=>node.depth&&node.data.kind==='directory'?22:7)(tree);
    tree.each(node=>{
      if(!node.depth)return;
      const data=node.data;
      const entry={...data,x:node.x0,y:node.y0,w:Math.max(0,node.x1-node.x0),d:Math.max(0,node.y1-node.y0),depth:node.depth};
      if(data.kind==='directory')districts.push(entry);
      if(!node.children)records.push(entry);
    });
    return {districts,records,unplaced,total:tree.value||0,cap:250};
  }
  function project(x,y,z,rotation=0){
    let a=x-350,b=y-220;
    for(let i=0;i<rotation;i++){const old=a;a=-b;b=old;}
    return {x:500+(a-b)*0.82,y:330+(a+b)*0.39-z};
  }
  function shape(entry,rotation=0,flat=false,max=1){
    const height=flat||entry.kind==='directory'||entry.kind==='reserve'?0:14+Math.log1p(entry.bytes)/Math.log1p(max)*92;
    const p=(x,y,z=0)=>project(x,y,z,rotation);
    const a=p(entry.x,entry.y,height),b=p(entry.x+entry.w,entry.y,height),c=p(entry.x+entry.w,entry.y+entry.d,height),d=p(entry.x,entry.y+entry.d,height);
    const b0=p(entry.x+entry.w,entry.y),c0=p(entry.x+entry.w,entry.y+entry.d),d0=p(entry.x,entry.y+entry.d);
    const polygon=points=>points.map(q=>`${q.x.toFixed(2)},${q.y.toFixed(2)}`).join(' ');
    return {...entry,top:polygon([a,b,c,d]),right:polygon([b,c,c0,b0]),left:polygon([d,c,c0,d0]),cx:(a.x+c.x)/2,cy:(a.y+c.y)/2,height,order:project(entry.x+entry.w/2,entry.y+entry.d/2,0,rotation).y};
  }
  root.CoreSpaceCity={buildCity,category,categories,shape,project};
  if(typeof module!=='undefined'&&module.exports)module.exports=root.CoreSpaceCity;
})(typeof window!=='undefined'?window:globalThis);

if(typeof Vue!=='undefined'){
window.FileCity={
  props:['items','pages','folder','active','loading','hasMore','error','revealBusy'],
  emits:['open','reveal','more','inspect'],
  setup(props,{emit}){
    const {ref,computed,watch}=Vue;
    const metric=ref('allocatedBytes'),flat=ref(false),rotation=ref(0),zoom=ref(1),pan=ref({x:0,y:0}),query=ref(''),filter=ref('all'),chosen=ref(null);
    const model=computed(()=>CoreSpaceCity.buildCity(props.items,props.pages,metric.value,props.folder));
    const max=computed(()=>Math.max(1,...model.value.records.map(node=>node.bytes)));
    const match=item=>(!query.value||item.name.toLocaleLowerCase().includes(query.value.toLocaleLowerCase()))&&(filter.value==='all'||CoreSpaceCity.category(item)===filter.value);
    const shapes=computed(()=>model.value.records.map(node=>CoreSpaceCity.shape(node,rotation.value,flat.value,max.value)).sort((a,b)=>a.order-b.order));
    const districts=computed(()=>model.value.districts.map(node=>CoreSpaceCity.shape(node,rotation.value,true,max.value)));
    const matches=computed(()=>{
      const seen=new Map();
      const selected=props.folder?.relativePath||'';
      for(const [parent,page] of Object.entries(props.pages)){
        if(page.loaded&&(parent===selected||!selected||parent.startsWith(selected+'/'))){
          for(const item of page.items)if(match(item))seen.set(item.relativePath,item);
        }
      }
      for(const item of props.items)if(match(item))seen.set(item.relativePath,item);
      return [...seen.values()];
    });
    const transform=computed(()=>`translate(${pan.value.x} ${pan.value.y}) translate(500 300) scale(${zoom.value}) translate(-500 -300)`);
    function reset(){zoom.value=1;pan.value={x:0,y:0};rotation.value=0;}
    function choose(node){chosen.value=node.kind==='reserve'?{...node.owner,groupBytes:node.bytes,groupName:node.name}:node.item||node.owner||node;}
    watch(()=>props.folder?.relativePath,()=>{chosen.value=null;query.value='';reset();});
    watch(()=>props.items,()=>{if(chosen.value){const all=[...model.value.records,...model.value.districts].map(n=>n.item).concat(model.value.unplaced);chosen.value=all.find(n=>n?.relativePath===chosen.value.relativePath)||null;}},{deep:true});
    let drag=null;
    function down(event){if(event.button!==0)return;drag={x:event.clientX,y:event.clientY,pan:{...pan.value},moved:false};event.currentTarget.setPointerCapture(event.pointerId);}
    function move(event){if(!drag)return;const scale=1000/event.currentTarget.getBoundingClientRect().width;const dx=(event.clientX-drag.x)*scale,dy=(event.clientY-drag.y)*scale;if(Math.abs(dx)+Math.abs(dy)>5)drag.moved=true;pan.value={x:drag.pan.x+dx,y:drag.pan.y+dy};}
    function up(event){const moved=drag?.moved;drag=null;if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);if(moved)event.preventDefault();}
    function wheel(event){zoom.value=Math.min(3,Math.max(.5,zoom.value*(event.deltaY<0?1.12:.88)));}
    const fmt=bytes=>formatBytes(bytes);
    function color(node){return CoreSpaceCity.categories[node.category||'reserve'].color;}
    const filterCategories=Object.fromEntries(Object.entries(CoreSpaceCity.categories).filter(([key])=>key!=='reserve'));
    return {metric,flat,rotation,zoom,pan,query,filter,chosen,model,shapes,districts,matches,transform,match,reset,choose,down,move,up,wheel,fmt,color,categories:CoreSpaceCity.categories,filterCategories,emit};
  },
  template:`<section class="file-city" aria-labelledby="city-title">
    <div class="city-heading"><div><span class="city-kicker">FILE CITY</span><h3 id="city-title">เมืองไฟล์</h3></div><label>ขนาดที่ใช้สร้างเมือง<select v-model="metric" aria-label="ขนาดที่ใช้สร้างเมือง"><option value="allocatedBytes">พื้นที่บนดิสก์</option><option value="logicalBytes">ขนาดเนื้อหา</option></select></label></div>
    <div class="city-toolbar"><button @click="flat=!flat" :aria-pressed="flat">{{flat?'มุมมองเมือง':'มุมมองแผนที่'}}</button><button @click="rotation=(rotation+1)%4">หมุนเมือง</button><button @click="zoom=Math.min(3,zoom+0.25)" :disabled="zoom>=3" aria-label="ขยายเมือง">＋</button><button @click="zoom=Math.max(.5,zoom-.25)" :disabled="zoom<=.5" aria-label="ย่อเมือง">−</button><button @click="reset">คืนมุมมอง</button><span>{{Math.round(zoom*100)}}%</span></div>
    <p class="city-status" v-if="active">กำลังสร้างเมืองจากรายการที่สแกนพบ ขนาดและตำแหน่งอาจเปลี่ยน</p>
    <p class="city-status" v-else-if="folder?.partial">ข้อมูลบางส่วน เมืองแสดงเฉพาะขนาดที่อ่านได้</p>
    <p class="error" v-if="error">โหลดเมืองไม่สำเร็จ: {{error}}</p>
    <div class="city-stage"><svg viewBox="0 0 1000 640" aria-label="แผนผังเมืองจากไฟล์และโฟลเดอร์" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up" @wheel.prevent="wheel">
      <defs><pattern id="city-grid" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M 40 0 L 0 0 0 40" fill="none" stroke="#d6e0dc" stroke-width=".6"/></pattern></defs>
      <rect width="1000" height="640" fill="#edf2ed"/><rect width="1000" height="640" fill="url(#city-grid)"/>
      <g :transform="transform">
        <g v-for="node in districts" :key="'district-'+node.item.relativePath" class="city-district" role="button" tabindex="0" :aria-label="'เลือกโฟลเดอร์ '+node.name" @pointerdown.stop @click="choose(node)" @keydown.enter.prevent="choose(node)"><title>{{node.item.relativePath}} · {{fmt(node.bytes)}} · โฟลเดอร์</title><polygon :points="node.top" fill="#d1e1d7" stroke="#679487" stroke-width="2"/><text :x="node.cx" :y="node.cy" text-anchor="middle" class="district-label" v-if="node.w>90&&node.d>35">{{node.name.slice(0,20)}}</text></g>
        <g v-for="node in shapes" :key="node.item?.relativePath || 'reserve-'+node.owner.relativePath+'-'+node.x" class="city-building" :class="{chosen:chosen?.relativePath===(node.item||node.owner)?.relativePath,dimmed:node.item&&!match(node.item)}" role="button" tabindex="0" :aria-label="'เลือก '+node.name" @pointerdown.stop @click="choose(node)" @dblclick="node.item?.kind==='directory'&&emit('open',node.item)" @keydown.enter.prevent="choose(node)">
          <title>{{node.item?.relativePath||node.owner?.relativePath}} · {{fmt(node.bytes)}} · {{node.kind==='reserve'?'ยังไม่แสดงรายละเอียด':categories[node.category].label}}</title>
          <polygon v-if="node.height" :points="node.left" :fill="color(node)" class="building-left"/><polygon v-if="node.height" :points="node.right" :fill="color(node)" class="building-right"/><polygon :points="node.top" :fill="color(node)" class="building-roof"/>
          <text v-if="node.w>95&&node.d>45" :x="node.cx" :y="node.cy" text-anchor="middle" class="building-label">{{node.name.slice(0,18)}}</text>
        </g>
      </g>
      <text v-if="!model.records.length" x="500" y="310" text-anchor="middle" class="city-empty">{{loading?'กำลังโหลดรายการ':items.length?'รายการเหล่านี้ยังไม่มีขนาดสำหรับวางบนเมือง':folder?.partial||active?'ยังไม่มีรายการที่อ่านได้':'โฟลเดอร์ว่าง'}}</text>
    </svg><span class="city-drag-hint">ลากพื้นที่ว่างเพื่อเลื่อน · เลื่อนล้อเมาส์เพื่อขยาย</span></div>
    <div class="city-districts" v-if="districts.length"><span class="small muted">ย่านโฟลเดอร์</span><button v-for="node in districts" :key="node.item.relativePath" @click="choose(node)" :aria-label="'เลือกย่าน '+node.name">▱ {{node.name}} · {{fmt(node.bytes)}}</button></div>
    <div class="city-details" v-if="chosen"><div><strong>{{chosen.name}}</strong><code>{{chosen.relativePath||'(โฟลเดอร์เริ่มต้น)'}}</code><span v-if="chosen.groupBytes!==undefined">{{chosen.groupName}} · {{fmt(chosen.groupBytes)}} ของย่านนี้</span><span>{{chosen.kind==='directory'?'โฟลเดอร์':chosen.kind==='link'?'ลิงก์':'ไฟล์'}} · เนื้อหา {{fmt(chosen.logicalBytes)}} · บนดิสก์ {{fmt(chosen.allocatedBytes)}}</span><span v-if="chosen.partial">ข้อมูลบางส่วน</span></div><div class="city-actions"><button v-if="chosen.kind==='directory'" @click="emit('open',chosen)">เข้าโฟลเดอร์</button><button @click="emit('inspect',chosen)">ดูในตาราง</button><button @click="emit('reveal',chosen)" :disabled="revealBusy!==null">เปิดตำแหน่ง</button></div></div>
    <p v-else class="small muted">เลือกแปลงหรืออาคารเพื่อดูชื่อ ขนาด และเปิดตำแหน่ง</p>
    <div class="city-legend"><span v-for="(type,key) in categories" :key="key"><i :style="{background:type.color}"></i>{{type.label}}</span></div>
    <p class="small muted">พื้นที่แปลงเทียบขนาด {{metric==='allocatedBytes'?'บนดิสก์':'เนื้อหา'}} · อาคารเป็นไฟล์ แปลงเป็นโฟลเดอร์ · ความสูงย่อสเกลเพื่อให้ไฟล์เล็กมองเห็น ไม่ใช่ความสูงต่อไบต์</p>
    <div class="city-find"><label>หาชื่อในเมือง<input v-model="query" placeholder="ชื่อไฟล์หรือโฟลเดอร์"></label><label>ประเภท<select v-model="filter" aria-label="ประเภทไฟล์ในเมือง"><option value="all">ทุกประเภท</option><option v-for="(type,key) in filterCategories" :key="key" :value="key">{{type.label}}</option></select></label></div>
    <div v-if="query||filter!=='all'" class="city-results"><p>พบ {{matches.length}} รายการในข้อมูลที่โหลดแล้ว</p><button v-for="item in matches.slice(0,30)" :key="item.relativePath" @click="choose(item)">{{item.name}}</button><span v-if="matches.length>30">แสดงชื่อ 30 รายการแรก ปรับคำค้นให้เจาะจงขึ้น</span></div>
    <details v-if="model.unplaced.length" class="city-unplaced"><summary>รายการที่ไม่อยู่บนแปลง {{model.unplaced.length}} รายการ (0 ไบต์หรือไม่ทราบ)</summary><button v-for="item in model.unplaced" :key="item.relativePath" @click="choose(item)">{{item.name}} · {{fmt(item[metric])}}</button></details>
    <p class="small muted">เมืองใช้รายการที่โหลดแล้วและลูกโฟลเดอร์ที่เปิดไว้ สูงสุด {{model.cap}} รายการต่อภาพ ส่วนที่ยังไม่แสดงเป็นแปลงสีเทา เลือกโฟลเดอร์เพื่อสำรวจต่อ</p>
    <button v-if="hasMore" @click="emit('more')" :disabled="loading">โหลดเมืองเพิ่มเติม 50 รายการ</button>
  </section>`
};
}
