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
    const windows=[];
    if(height>30&&entry.w>5&&entry.d>5){
      const corners=[[entry.x,entry.y],[entry.x+entry.w,entry.y],[entry.x+entry.w,entry.y+entry.d],[entry.x,entry.y+entry.d]];
      const front=corners.map((q,i)=>({i,y:p(q[0],q[1]).y})).sort((a,b)=>b.y-a.y)[0].i;
      for(const [i,j] of [[(front+3)%4,front],[front,(front+1)%4]]){
        const u=corners[i],v=corners[j];const columns=Math.min(6,Math.max(1,Math.floor(Math.hypot(v[0]-u[0],v[1]-u[1])/45)));
        for(let col=0;col<columns;col++)for(let row=0;row<3;row++){
          const left=(col+.28)/columns,right=(col+.7)/columns,z=height*(row+.25)/3;
          const q=(t,z)=>p(u[0]+(v[0]-u[0])*t,u[1]+(v[1]-u[1])*t,z);
          windows.push(polygon([q(left,z),q(right,z),q(right,z+height*.12),q(left,z+height*.12)]));
        }
      }
    }
    const roof=[a,b,c,d],ground=[p(entry.x,entry.y),b0,c0,d0];
    const front=ground.map((point,i)=>({i,y:point.y})).sort((u,v)=>v.y-u.y)[0].i;
    const prev=(front+3)%4,next=(front+1)%4;
    return {...entry,windows,top:polygon(roof),right:polygon([roof[front],roof[next],ground[next],ground[front]]),left:polygon([roof[prev],roof[front],ground[front],ground[prev]]),cx:(a.x+c.x)/2,cy:(a.y+c.y)/2,height,order:project(entry.x+entry.w/2,entry.y+entry.d/2,0,rotation).y};
  }
  root.CoreSpaceCity={buildCity,category,categories,shape,project};
  if(typeof module!=='undefined'&&module.exports)module.exports=root.CoreSpaceCity;
})(typeof window!=='undefined'?window:globalThis);

if(typeof Vue!=='undefined'){
window.FileCity={
  props:['items','pages','folder','active','loading','hasMore','error','revealBusy','scanId','viewMode','search','locate'],
  emits:['open','reveal','more','inspect','activity'],
  setup(props,{emit}){
    const {ref,computed,watch,onUnmounted}=Vue;
    const metric=ref('allocatedBytes'),flat=ref(false),rotation=ref(0),zoom=ref(1),pan=ref({x:0,y:0}),query=ref(''),filter=ref('all'),chosen=ref(null);
    const model=computed(()=>CoreSpaceCity.buildCity([...props.items].sort((a,b)=>Number(b.relativePath===chosen.value?.relativePath)-Number(a.relativePath===chosen.value?.relativePath)),props.pages,metric.value,props.folder));
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
    function choose(node,focus=false){
      chosen.value=node.kind==='reserve'?{...node.owner,groupBytes:node.bytes,groupName:node.name}:node.item||node.owner||node;
      if(focus){Vue.nextTick(()=>{const target=shapes.value.find(x=>x.item?.relativePath===chosen.value?.relativePath);if(target){zoom.value=Math.min(6,Math.max(1,100/Math.max(target.w,target.d)));pan.value={x:-(target.cx-500)*zoom.value,y:-(target.cy-300)*zoom.value};}});}
    }
    watch(()=>props.folder?.relativePath,()=>{chosen.value=null;reset();});
    watch(()=>props.items,()=>{if(chosen.value){const all=[...model.value.records,...model.value.districts].map(n=>n.item).concat(model.value.unplaced);chosen.value=all.find(n=>n?.relativePath===chosen.value.relativePath)||null;}},{deep:true});
    let drag=null;
    function down(event){if(event.button!==0)return;drag={x:event.clientX,y:event.clientY,pan:{...pan.value},moved:false};event.currentTarget.setPointerCapture(event.pointerId);}
    function move(event){if(!drag)return;const scale=1000/event.currentTarget.getBoundingClientRect().width;const dx=(event.clientX-drag.x)*scale,dy=(event.clientY-drag.y)*scale;if(Math.abs(dx)+Math.abs(dy)>5)drag.moved=true;pan.value={x:drag.pan.x+dx,y:drag.pan.y+dy};}
    function up(event){const moved=drag?.moved;drag=null;if(event.currentTarget.hasPointerCapture(event.pointerId))event.currentTarget.releasePointerCapture(event.pointerId);if(moved)event.preventDefault();}
    function wheel(event){zoom.value=Math.min(6,Math.max(.5,zoom.value*(event.deltaY<0?1.12:.88)));}
    const fmt=bytes=>formatBytes(bytes);
    function color(node){return CoreSpaceCity.categories[node.category||'reserve'].color;}
    const hovered=ref(null),hoverPoint=ref({x:10,y:10}),labels=ref(true),searching=ref(false),searchError=ref(''),serverResults=ref(null),searchTotal=ref(0),searchMore=ref(false);
    const inspected=computed(()=>chosen.value||props.folder);
    const ground=computed(()=>CoreSpaceCity.shape({x:0,y:0,w:700,d:440,kind:'directory',bytes:0},rotation.value,true,1).top);
    const chosenPin=computed(()=>{if(!chosen.value)return null;const node=shapes.value.find(x=>x.item?.relativePath===chosen.value.relativePath);return node?{x:500+(node.cx-500)*zoom.value+pan.value.x,y:300+(node.cy-300)*zoom.value+pan.value.y,name:node.name}:null;});
    const hints=computed(()=>zoom.value>1.5&&chosen.value?[]:shapes.value.filter(n=>n.item&&n.w*n.d<6000).sort((a,b)=>b.bytes-a.bytes).slice(0,12).map((node,i)=>({node,x:i%2?810:18,y:125+Math.floor(i/2)*60,targetX:500+(node.cx-500)*zoom.value+pan.value.x,targetY:300+(node.cy-300)*zoom.value+pan.value.y})));
    function hover(node,event){hovered.value=node;const rect=event.currentTarget.closest('svg').getBoundingClientRect();hoverPoint.value={x:Math.max(8,Math.min(rect.width-250,event.clientX-rect.left+12)),y:Math.max(8,event.clientY-rect.top-60)};}
    function clearHover(){hovered.value=null;}
    let searchGeneration=0,searchTimer;
    async function runSearch(more=false){
      clearTimeout(searchTimer);
      const generation=++searchGeneration;searching.value=true;searchError.value='';const term=query.value.trim();
      emit('activity',`ค้นหา “${term}” ในผลสแกนจริง`);
      try{
        const result=await props.search(term,more?(serverResults.value?.length||0):0);
        if(generation!==searchGeneration)return;
        if(result.scanId!==props.scanId||!Array.isArray(result.items))throw Error('อ่านผลค้นหาไม่ได้');
        serverResults.value=more?[...serverResults.value,...result.items]:result.items;searchTotal.value=result.total;searchMore.value=result.hasMore;
        emit('activity',`ค้นหา “${term}” พบ ${result.total} รายการ${result.partial?' · ข้อมูลยังไม่ครบ':''}`);
      }catch(error){if(generation===searchGeneration){searchError.value=error.message;emit('activity',`ค้นหาไม่สำเร็จ: ${error.message}`);}}
      finally{if(generation===searchGeneration)searching.value=false;}
    }
    watch(query,()=>{clearTimeout(searchTimer);searchGeneration++;searchError.value='';serverResults.value=null;searchMore.value=false;if(!query.value.trim()){searching.value=false;return;}searching.value=true;searchTimer=setTimeout(()=>runSearch(),250);});
    watch(()=>props.scanId,()=>{query.value='';chosen.value=null;});
    watch(()=>props.active,(active,previous)=>{if(previous&&!active&&query.value.trim())runSearch();});
    onUnmounted(()=>{clearTimeout(searchTimer);searchGeneration++;});
    const extension=item=>item?.kind==='directory'?'▱':item?.name?.includes('.')?item.name.split('.').pop().toUpperCase().slice(0,5):'FILE';
    const shownResults=computed(()=>serverResults.value||[]);
    return {metric,flat,rotation,zoom,pan,query,filter,chosen,model,shapes,districts,matches,transform,match,reset,choose,down,move,up,wheel,fmt,color,categories:CoreSpaceCity.categories,emit,hovered,hoverPoint,hover,clearHover,labels,hints,inspected,ground,chosenPin,searching,searchError,shownResults,searchTotal,searchMore,runSearch,extension};
  },
  template:`<section class="file-city">
    <div class="city-search"><label class="search-input">ค้นไฟล์ในผลสแกน<input v-model="query" maxlength="200" placeholder="ค้นชื่อไฟล์หรือเส้นทาง…" aria-label="ค้นไฟล์ในผลสแกน"></label><span v-if="searching" role="status">กำลังค้นหา…</span><span v-else-if="query.trim()&&!searchError" role="status">พบ {{searchTotal}} รายการ</span><p v-if="searchError" class="error" role="alert">{{searchError}} <button @click="runSearch()">ลองใหม่</button></p></div>
    <div v-if="query.trim()" class="search-result-list"><button v-for="item in shownResults" :key="item.relativePath" @click="locate(item)"><strong>{{item.name}}</strong><span>{{item.relativePath}}</span><b>{{fmt(item.allocatedBytes)}}</b></button><p v-if="!searching&&!shownResults.length&&!searchError">ไม่พบชื่อที่ตรงกับคำค้น</p><button v-if="searchMore" @click="runSearch(true)" :disabled="searching">ผลค้นหาเพิ่มเติม</button></div>
    <div class="scene-layout"><div class="scene-content">
    <template v-if="viewMode==='city'">
      <div class="city-toolbar"><button @click="flat=!flat" :aria-pressed="flat">{{flat?'เมือง':'แผนที่'}}</button><button @click="rotation=(rotation+1)%4" aria-label="หมุนเมือง">↻</button><button @click="zoom=Math.min(6,zoom+.5)" :disabled="zoom>=6" aria-label="ขยายเมือง">＋</button><button @click="zoom=Math.max(.5,zoom-.5)" :disabled="zoom<=.5" aria-label="ย่อเมือง">−</button><button @click="reset">คืนมุมมอง</button><label><input type="checkbox" v-model="labels">ชื่อไฟล์</label><span>{{Math.round(zoom*100)}}%</span></div>
      <p v-if="error" class="error">{{error}}</p>
      <div class="city-stage"><svg viewBox="0 0 1000 640" aria-label="เมืองจากไฟล์จริง" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up" @wheel.prevent="wheel">
        <defs><pattern id="city-grid" width="40" height="40" patternUnits="userSpaceOnUse"><path d="M40 0H0V40" fill="none" stroke="#bacdc8" stroke-width=".5"/></pattern><filter id="city-shadow" x="-50%" y="-50%" width="200%" height="200%"><feDropShadow dx="3" dy="6" stdDeviation="4" flood-opacity=".18"/></filter></defs>
        <rect width="1000" height="640" fill="#e3eeea"/><rect width="1000" height="640" fill="url(#city-grid)"/>
        <g :transform="transform">
          <polygon :points="ground" fill="#85998f" stroke="#c6d7ce" stroke-width="4"/>
          <g v-for="node in districts" :key="node.item.relativePath" class="city-district" role="button" tabindex="0" :aria-label="'เลือกโฟลเดอร์ '+node.name" @pointerdown.stop @click="choose(node)" @keydown.enter.prevent="choose(node)" @keydown.space.prevent="choose(node)" @mouseenter="hover(node,$event)" @mouseleave="clearHover"><polygon :points="node.top" fill="#b9d5c8" stroke="#668d81" stroke-width="2"/></g>
          <g v-for="node in shapes" :key="node.item?.relativePath||'group-'+node.x" class="city-building" :class="{chosen:chosen?.relativePath===(node.item||node.owner)?.relativePath}" role="button" tabindex="0" :aria-label="'เลือก '+node.name" @pointerdown.stop @click="choose(node)" @keydown.enter.prevent="choose(node)" @keydown.space.prevent="choose(node)" @focus="hovered=node" @blur="clearHover" @mouseenter="hover(node,$event)" @mouseleave="clearHover">
            <polygon v-if="node.height" :points="node.left" :fill="color(node)" class="building-left"/><polygon v-if="node.height" :points="node.right" :fill="color(node)" class="building-right"/><polygon :points="node.top" :fill="color(node)" class="building-roof"/>
            <polygon v-for="(window,i) in node.windows" :key="i" :points="window" fill="#d9f1e8" opacity=".55" class="city-window"/>
            <g v-if="node.w*node.d*zoom*zoom>6000"><text :x="node.cx" :y="node.cy-8/zoom" :style="{fontSize:15/zoom+'px'}" text-anchor="middle" class="building-type">{{extension(node.item)}}</text><text v-if="labels" :x="node.cx" :y="node.cy+14/zoom" :style="{fontSize:13/zoom+'px'}" text-anchor="middle" class="building-label">{{node.name.slice(0,30)}}</text></g>
          </g>
        </g>
        <g v-if="labels" class="name-callouts"><g v-for="hint in hints" :key="hint.node.item.relativePath" role="button" tabindex="0" :aria-label="'ชื่อ '+hint.node.name" @pointerdown.stop @click="choose(hint.node,true)" @keydown.enter.prevent="choose(hint.node,true)"><line :x1="hint.x+85" :y1="hint.y" :x2="hint.targetX" :y2="hint.targetY" stroke="#46695e" stroke-width=".8" stroke-dasharray="3 3"/><rect :x="hint.x" :y="hint.y-20" width="175" height="40" rx="6" fill="#fffffff0" stroke="#b0c6bd"/><text :x="hint.x+8" :y="hint.y-3">{{hint.node.name.slice(0,24)}}</text><text :x="hint.x+8" :y="hint.y+12" class="callout-size">{{fmt(hint.node.bytes)}}</text></g></g>
        <g v-if="chosenPin" class="chosen-pin" pointer-events="none"><circle :cx="chosenPin.x" :cy="chosenPin.y" r="7" fill="#fff" stroke="#183f31" stroke-width="3"/><rect :x="chosenPin.x+12" :y="chosenPin.y-32" width="235" height="28" rx="5" fill="#183f31"/><text :x="chosenPin.x+20" :y="chosenPin.y-13" fill="white" font-size="13">{{chosenPin.name.slice(0,32)}}</text></g>
        <text v-if="!model.records.length" x="500" y="310" text-anchor="middle" class="city-empty">{{loading?'กำลังโหลด…':folder?.partial||active?'ยังไม่มีข้อมูลที่อ่านได้':'ไม่มีไฟล์ที่มีพื้นที่สำหรับวาด'}}</text>
      </svg><div v-if="hovered" class="file-tooltip" role="tooltip" :style="{left:hoverPoint.x+'px',top:hoverPoint.y+'px'}"><strong>{{hovered.name}}</strong><span>{{fmt(hovered.bytes)}} · คลิกเพื่อเลือก</span></div><span class="city-drag-hint">ลากพื้นเพื่อเลื่อน · ล้อเมาส์เพื่อขยาย</span></div>
      <div class="city-districts" v-if="districts.length"><button v-for="node in districts" :key="node.item.relativePath" @click="emit('open',node.item)">▱ {{node.name}}</button></div>
      <details v-if="model.unplaced.length" class="city-unplaced"><summary>0 ไบต์ / ไม่ทราบขนาด · {{model.unplaced.length}} รายการ</summary><button v-for="item in model.unplaced" :key="item.relativePath" @click="choose(item)">{{item.name}} · {{fmt(item[metric])}}</button></details>
      <button v-if="hasMore" @click="emit('more')" :disabled="loading">โหลดอีก 50 รายการ</button>
    </template>
    <div v-else-if="!query.trim()" class="list-view"><slot></slot></div>
    </div>
    <aside class="file-inspector" aria-label="รายละเอียดที่เลือก"><span class="inspector-kind">{{inspected?.kind==='directory'?'โฟลเดอร์':'ไฟล์'}}{{chosen?'ที่เลือก':''}}</span><h2>{{inspected?.name}}</h2><strong class="inspector-size">{{fmt(inspected?.allocatedBytes)}}</strong><span class="small muted">พื้นที่บนดิสก์</span><p v-if="inspected?.partial" class="partial-note">ข้อมูลบางส่วน</p><p v-if="inspected?.groupBytes!==undefined">ส่วนที่รวม {{fmt(inspected.groupBytes)}}</p>
      <div class="inspector-actions"><button v-if="chosen?.kind==='directory'&&chosen.relativePath!==folder?.relativePath" @click="emit('open',chosen)">เข้าโฟลเดอร์</button><button @click="emit('reveal',inspected)" :disabled="revealBusy!==null">เปิดตำแหน่ง</button><button v-if="chosen" @click="emit('inspect',chosen)">ดูในรายการ</button></div>
      <details class="file-metadata"><summary>ข้อมูลไฟล์</summary><code>{{inspected?.relativePath||'(โฟลเดอร์เริ่มต้น)'}}</code><dl><dt>ขนาดเนื้อหา</dt><dd>{{fmt(inspected?.logicalBytes)}}</dd><dt>ประเภท</dt><dd>{{inspected?.kind==='directory'?'โฟลเดอร์':extension(inspected)}}</dd></dl></details>
      <details class="city-help"><summary>วิธีอ่านเมือง</summary><p>แปลงเทียบขนาดไฟล์ อาคารสูงใช้พื้นที่มากกว่า ความสูงย่อสเกลเพื่อให้มองเห็น หน้าต่างเป็นองค์ประกอบภาพ</p><p>คลิกอาคารเพื่อเลือก รายการเล็กค้นชื่อแล้วคลิกผลเพื่อซูมไปยังไฟล์ได้</p><p>สีเทาคือส่วนที่ยังไม่แสดงรายละเอียด วาดได้ {{model.cap}} รายการต่อภาพ</p><div class="city-legend"><span v-for="(type,key) in categories" :key="key"><i :style="{background:type.color}"></i>{{type.label}}</span></div><label>ขนาดที่ใช้<select v-model="metric" aria-label="ขนาดที่ใช้สร้างเมือง"><option value="allocatedBytes">บนดิสก์</option><option value="logicalBytes">เนื้อหา</option></select></label></details>
    </aside></div>
  </section>`
};
}
