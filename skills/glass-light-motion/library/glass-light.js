/* glass-light blocks (Grey "Bevel 3.0"), measured per frame from the source at 25 fps (work/glass-light/rep/states.json).
   Every block is a pure function of t, registered as a frame drawer, so a seek to any frame renders the same picture.
   Blocks: centredLine (arrival colour steps + re-centre law + trim glide), labelField (3D name · value field on the creep /
   cut-in / ease-out camera; names cut off, values fade, separator dots stay), roll (word rolls up across a cut to the brand
   word), bloom (soft ellipse that grows into the background), dotsToMark (white lines draw out of the standing dots, then glass).
   Measured constants are named and commented with the frames they came from; nothing here holds source content. */
(function(){
const F=25, fr=n=>n/F, clamp=(v,a=0,b=1)=>Math.min(b,Math.max(a,v)), lerp=(a,b,k)=>a+(b-a)*k;
const rgb=(c)=>`rgb(${c.map(Math.round).join(',')})`, mixc=(a,b,k)=>a.map((v,i)=>lerp(v,b[i],k));
const GL={
  FONT:"'SF Pro Display'", WEIGHT:500, SIZE:76.7, TRACK:'-0.01em', GAP:17,          // glyph IoU 0.751, aspect 8.045 vs 8.044
  PAPER:[253,253,253], INK:[29,29,30],
  PRE:[208,224,255],   // arrival frame (word at partial opacity, palest periwinkle)
  P0:[122,165,255],    // first full frame
  FADE:[150,180,245],  // a trimmed word's colour on its last frame
  BRAND:[26,102,255], // the brand word
  RE:0.343, TAU:0.23,  // re-centre: 66% on the arrival frame, the rest decays with tau 0.23 s (frames 11–23)
  MESH_CORE:[138,167,250], MESH_EDGE:[193,204,252],
  BLOOM_R:[0,167,257,320,373,425,475,535,597,674,750],   // equivalent radius per frame from bloom start (frames 126–136)
  BLOOM_ASPECT:1.9,
};
// a word settles from P0 to ink over 5 frames (≤5 letters) up to 12 (7 letters)
const settleFrames=w=>Math.round(5+Math.max(0,w.replace(/[^A-Za-z0-9]/g,'').length-4)*2.33);

/* centredLine(parent, words, times, opts) — one line on the centre. trimAt: time the leading words start to leave
   (the line then glides expo in-out over 29 frames onto the last word); out: time the whole line leaves (cut). */
function centredLine(p,words,times,{y=540,size=GL.SIZE,trimAt=null,keep=1,out=null,brandIdx=[],scale=()=>1,dy=()=>0}={}){
  const L=document.createElement('div'); L.style.cssText=`position:absolute;left:0;top:0;white-space:nowrap;font-family:${GL.FONT};font-weight:${GL.WEIGHT};font-size:${size}px;letter-spacing:${GL.TRACK};transform-origin:0 0`;
  L.innerHTML=words.map((w,i)=>`<span style="display:inline-block;margin-right:${i<words.length-1?GL.GAP*size/GL.SIZE:0}px">${w}</span>`).join('');
  p.appendChild(L); const ws=[...L.children], xs=ws.map(s=>s.offsetLeft), xe=ws.map(s=>s.offsetLeft+s.offsetWidth);
  const T=(j,k)=>960-(xe[k]-xs[j])/2-xs[j], n=words.length, first=n-keep;
  const lineX=t=>{ let x=T(0,0)+70*size/GL.SIZE/GL.RE, tk=-1, Tk=T(0,0);
    for(let i=0;i<n;i++){ const ta=times[i]; if(t<ta) break; const xb=tk<0?x:Tk+(x-Tk)*GL.RE*Math.exp(-(ta-tk)/GL.TAU); x=xb; tk=ta; Tk=T(0,i); }
    let X=Tk+(x-Tk)*GL.RE*Math.exp(-(t-tk)/GL.TAU);
    if(trimAt!=null){ const g0=trimAt+fr(7), g1=g0+fr(29);
      if(t>=g0){ const X0=Tk+(x-Tk)*GL.RE*Math.exp(-(g0-tk)/GL.TAU), u=clamp((t-g0)/(g1-g0)); const e=u<.5?Math.pow(2,20*u-10)/2:(2-Math.pow(2,-20*u+10))/2; X=lerp(X0,T(first,n-1),e); } }
    return X; };
  const ST=words.map(settleFrames);
  return t=>{
    const s=scale(t), X=lineX(t);
    L.style.display=(out!=null&&t>=out)||t<times[0]?'none':'block';
    L.style.transform=`translate(${960+(X-960)*s}px,${y+(-14)*s-0.62*size*s+dy(t)}px) scale(${s})`;
    ws.forEach((w,i)=>{ const f=(t-times[i])*F;
      if(f<0){ w.style.opacity=0; return; } w.style.opacity=1;
      let c;
      if(brandIdx.includes(i)) c=f<1?GL.PRE:mixc(GL.P0,GL.BRAND,clamp((f-1)/3));
      else c=f<1?GL.PRE:mixc(GL.P0,GL.INK,clamp((f-1)/(ST[i]-1)));
      if(trimAt!=null && i<first){ const k=i, fs=(t-trimAt)*F-[0,3,7,10,13,16,19,22][Math.min(k,7)];
        if(fs>=0){ c=mixc(GL.INK,GL.FADE,clamp(fs/12)); if(fs>=13) w.style.opacity=0; } }
      const lead=(cc)=>{ if(trimAt!=null && i<first && (t-trimAt)*F>=0) return cc; return cc; };
      if(f>=1 && f<ST[i]+1 && !(trimAt!=null && i<first && (t-trimAt)*F-[0,3,7,10,13,16,19,22][Math.min(i,7)]>=0)){
        const fn=(ff)=>brandIdx.includes(i)?mixc(GL.P0,GL.BRAND,clamp((ff-1)/3)):mixc(GL.P0,GL.INK,clamp((ff-1)/(ST[i]-1)));
        w.style.color='transparent'; w.style.backgroundImage=`linear-gradient(90deg, ${rgb(fn(f+1.1))}, ${rgb(fn(f-0.9))})`; w.style.webkitBackgroundClip='text'; w.style.backgroundClip='text';
      } else { w.style.backgroundImage='none'; w.style.color=rgb(c); }
      if(f<1) w.style.opacity=0.42; });
  };
}

/* the camera on the word and the field, from the moment the field starts (t0): creep, hard cut-in at +0.24 s, ease out.
   Word-plane scale (frames 66–110) and label-plane scale (frames 66–110, second jump at +0.80 s). */
const SD=[[0,1],[0.20,1.037],[0.24,1.096],[0.25,1.341],[0.36,1.422],[0.48,1.459],[0.60,1.489],[0.84,1.519],[1.12,1.526]];
const SL=[[0,.47],[0.20,.535],[0.24,.535],[0.25,.70],[0.36,.78],[0.56,.857],[0.72,.888],[0.76,.895],[0.80,.958],[0.88,.985],[0.96,1.0],[1.12,1.025],[1.28,1.045],[1.86,1.075]];
const tab=(T,u)=>{ if(u<=T[0][0]) return T[0][1]; for(let i=1;i<T.length;i++) if(u<T[i][0]){ const [a,x]=T[i-1],[b,y]=T[i]; return lerp(x,y,(u-a)/(b-a)); } return T.at(-1)[1]; };
const camera=t0=>({word:t=>t<t0?1:tab(SD,t-t0), field:t=>tab(SL,t-t0)});

/* labelField(parent, labels, t0, opts): labels = [{n, v, x, y, rot, keepDot}] at their rest positions (scale 1, which the
   field reaches at t0+0.96). Names cut off in the given order from t0+1.24, values fade over 8 frames, kept dots stay.
   A mirrored ghost of the same field sits behind (blur 7, opacity 0.3), as in the source. */
function labelField(p,labels,t0,{nameOff=null,size=41,ghost=true,dotsUntil=1e9}={}){
  const cam=camera(t0), N=[];
  const mk=(o,i,back)=>{ const d=document.createElement('div');
    d.style.cssText=`position:absolute;left:0;top:0;white-space:nowrap;font-family:${GL.FONT};font-weight:500;font-size:${size}px;letter-spacing:-0.01em;display:flex;align-items:center;transform-origin:0 50%`;
    d.innerHTML=`<span style="color:rgb(31,32,35)">${o.n}</span><span style="width:8px;height:8px;border-radius:50%;background:rgb(77,141,255);box-shadow:0 0 0 3px rgba(255,255,255,.9),0 1px 4px rgba(120,130,200,.35);margin:0 18px;flex:none"></span><span style="color:rgb(77,141,255)">${o.v}</span>`;
    p.appendChild(d); N.push({d,o,i,back}); };
  labels.forEach((o,i)=>mk(o,i,false)); if(ghost) labels.forEach((o,i)=>mk({...o,x:960-(o.x+150-960)*1.22-150,y:540+(o.y-540)*1.18-30},i,true));
  const order=nameOff||labels.map((_,i)=>i);
  return t=>{ const s=cam.field(t), far=clamp((1-s)/0.45);
    for(const {d,o,i,back} of N){
      if(t<t0||t>=dotsUntil){ d.style.display='none'; continue; } d.style.display='flex';
      const sc=s*(back?0.9:1), on=clamp((t-t0-0.012*i)/0.24);
      d.style.transform=`translate(${960+(o.x-960)*sc}px,${540+(o.y-540)*sc}px) translateY(-50%) scale(${back?-sc:sc},${sc}) rotate(${o.rot||0}deg)`;
      const k=order.indexOf(i), off=t0+1.16+k*fr(1.6);
      const nOut=back?clamp((t-t0-1.06)/0.3):(t>=off?1:0), vOut=back?clamp((t-t0-1.16)/0.3):clamp((t-off-fr(2))/fr(8));
      d.style.opacity=(on*(back?0.3:1)*(back?1-vOut:1)).toFixed(3);
      d.style.filter=`blur(${back?7:(far*4).toFixed(2)}px)`;
      const [n,dot,v]=d.children; n.style.color=rgb(mixc([31,32,35],[178,188,236],back?0.6:far)); n.style.opacity=1-nOut; v.style.opacity=1-vOut;
      dot.style.opacity=back?1-vOut:(o.keepDot?1:1-vOut); }
  };
}
/* where a label's separator dot sits on screen at time t (to hand the dots over to the mark) */
function dotAt(o,t,t0,size=41,nameW){ const s=camera(t0).field(t); return {x:960+(o.x+nameW+18+4-960)*s, y:540+(o.y-540)*s}; }

/* labelField3D(parent, front, t0, opts): the source's field as a real 3D space. front = [{n,v,x,y,rot,keepDot}] at rest
   positions (screen, scale 1 at t0+0.96); behind it two more planes of labels (mid mirrored, back plain) at depth, all on one
   camera whose front-plane scale follows the measured table (creep, cut-in, ease out), with a slow roll of the whole space.
   Depth gives parallax, blur and atmospheric fade; names cut off in order, values fade, kept dots stay. */
function labelField3D(p,front,t0,{nameOff=null,size=41,mid=[],back=[],dotsUntil=1e9,roll=[-1.5,1]}={}){
  const Zf=640, F=295.3, c=t=>Zf-F/tab(SL,t-t0);
  const mk=(o,i,Z,kind)=>{ const d=document.createElement('div');
    d.style.cssText=`position:absolute;left:0;top:0;white-space:nowrap;font-family:${GL.FONT};font-weight:500;font-size:${size}px;letter-spacing:-0.01em;display:flex;align-items:center;transform-origin:0 50%`;
    d.innerHTML=`<span style="color:rgb(31,32,35)">${o.n}</span><span style="width:8px;height:8px;border-radius:50%;background:rgb(77,141,255);box-shadow:0 0 0 3px rgba(255,255,255,.9),0 1px 4px rgba(120,130,200,.35);margin:0 18px;flex:none"></span><span style="color:rgb(77,141,255)">${o.v}</span>`;
    p.appendChild(d); const X=(o.x-960)*(Z-(Zf-F))/F, Y=(o.y-540)*(Z-(Zf-F))/F; return {d,o,i,Z,X,Y,kind}; };
  const N=[...front.map((o,i)=>mk(o,i,Zf,'front')),...mid.map((o,i)=>mk(o,i,800,'mid')),...back.map((o,i)=>mk(o,i,1000,'back'))];
  const order=nameOff||front.map((_,i)=>i);
  return t=>{ const cz=c(t), u=clamp((t-t0)/2.2), th=(roll[0]+(roll[1]-roll[0])*u)*Math.PI/180, co=Math.cos(th), si=Math.sin(th);
    for(const q of N){ const {d,o,i,Z,kind}=q;
      if(t<t0||t>=dotsUntil){ d.style.display='none'; continue; } d.style.display='flex';
      const s=F/(Z-cz); const X=q.X*co-q.Y*si, Y=q.X*si+q.Y*co; const sx=960+X*s/((Z-(Zf-F))/F)*((Z-(Zf-F))/F), sy=540+Y*s;
      const px=960+X*s, py=540+Y*s;
      const sf=tab(SL,t-t0), far=clamp((1-sf)/0.45), on=clamp((t-t0-0.012*i-(kind==='front'?0:kind==='mid'?-0.1:-0.2))/0.3);
      /* spherical lens: barrel the position, and turn each tag to face the centre (yaw with x, pitch with y) */
      d.style.transform=`translate(${px}px,${py}px) translateY(-50%) scale(${kind==='mid'?-s:s},${s}) rotate(${(o.rot||0)+th*57.3}deg)`;
      const [n,dot,v]=d.children;
      if(kind==='front'){ const k=order.indexOf(i), off=t0+1.16+k*fr(1.6), nOut=t>=off?1:0, vOut=clamp((t-off-fr(2))/fr(8));
        d.style.opacity=on.toFixed(3); d.style.filter=`blur(${(far*4).toFixed(2)}px)`;
        n.style.color=rgb(mixc([31,32,35],[170,195,250],far)); n.style.opacity=1-nOut; v.style.opacity=1-vOut; dot.style.opacity=o.keepDot?1:1-vOut; }
      else { /* depth of field: circle of confusion grows with distance behind the focal plane (the front tags) */
        const coc=Math.min(16,14*Math.abs(Z-Zf)/Math.max(60,Z-cz)), fade=1-clamp((t-t0-1.0)/0.4), haze=clamp((Z-Zf)/600)*0.45, a=kind==='mid'?0.8:0.62;
        d.style.opacity=(on*a*fade).toFixed(3); d.style.filter=`blur(${coc.toFixed(2)}px)`;
        n.style.color=rgb(mixc([31,32,35],[253,253,253],haze)); v.style.color=rgb(mixc([77,141,255],[253,253,253],haze*0.6)); } }
  };
}
/* where a front label's dot is on screen at time t (rolled), for handing dots to the mark */
function dot3D(o,nameW,t,t0,roll=[-1.5,1]){ const Zf=640,F=295.3, cz=Zf-F/tab(SL,t-t0), s=F/(Zf-cz), u=clamp((t-t0)/2.2), th=(roll[0]+(roll[1]-roll[0])*u)*Math.PI/180;
  const X=(o.x+nameW+22-960), Y=(o.y-540); const dx=(X*Math.cos(th)-Y*Math.sin(th))*s, dy=(X*Math.sin(th)+Y*Math.cos(th))*s; const b=lensAt(960+dx,540+dy); return b; }

const LENS_K=0.10;
function lensAt(x,y){ const dx=(x-960)/960, dy=(y-540)/960, r2=dx*dx+dy*dy, f=1+LENS_K*r2; return {x:960+(x-960)*f, y:540+(y-540)*f}; }
let LENSMAP=null;
function lensMap(){ if(LENSMAP) return LENSMAP; const W=480,H=270,c=document.createElement('canvas'); c.width=W; c.height=H; const g=c.getContext('2d'), im=g.createImageData(W,H), S=160;
  for(let j=0;j<H;j++) for(let i=0;i<W;i++){ const x=i/W*1920, y=j/H*1080, dx=(x-960)/960, dy=(y-540)/960, r2=dx*dx+dy*dy, f=1/(1+LENS_K*r2);
    const sx=960+(x-960)*f, sy=540+(y-540)*f, k=(j*W+i)*4; im.data[k]=Math.round(clamp(0.5+(sx-x)/S)*255); im.data[k+1]=Math.round(clamp(0.5+(sy-y)/S)*255); im.data[k+2]=128; im.data[k+3]=255; }
  g.putImageData(im,0,0); LENSMAP=c.toDataURL(); return LENSMAP; }
function lensLayer(p){ const NS='http://www.w3.org/2000/svg';
  if(!document.getElementById('gl-lens')){ const s=document.createElementNS(NS,'svg'); s.setAttribute('width',0); s.setAttribute('height',0); s.style.position='absolute';
    s.innerHTML=`<filter id="gl-lens" x="0" y="0" width="1920" height="1080" filterUnits="userSpaceOnUse" color-interpolation-filters="sRGB"><feImage href="${lensMap()}" x="0" y="0" width="1920" height="1080" preserveAspectRatio="none" result="m"/><feDisplacementMap in="SourceGraphic" in2="m" scale="160" xChannelSelector="R" yChannelSelector="G"/></filter>`; document.body.appendChild(s); }
  const w=document.createElement('div'); w.style.cssText='position:absolute;inset:0;filter:url(#gl-lens)'; p.appendChild(w);
  const soft=document.createElement('div'); soft.style.cssText='position:absolute;inset:0;pointer-events:none;-webkit-backdrop-filter:blur(5px);backdrop-filter:blur(5px);-webkit-mask-image:radial-gradient(62% 70% at 50% 50%,transparent 55%,#000 100%);mask-image:radial-gradient(62% 70% at 50% 50%,transparent 55%,#000 100%)';
  const wash=document.createElement('div'); wash.style.cssText='position:absolute;inset:0;pointer-events:none;background:radial-gradient(70% 78% at 50% 50%,rgba(253,253,253,0) 55%,rgba(253,253,253,.6) 100%)';
  return {layer:w, edges:[soft,wash]}; }

/* roll(parent, from, to, tCut): the word drifts up accelerating for 0.4 s, cut to the brand word just below, which settles up. */
function roll(p,word,tCut,{size=GL.SIZE,scale=()=>1}={}){
  const b=document.createElement('div'); b.style.cssText=`position:absolute;left:960px;top:0;white-space:nowrap;font-family:${GL.FONT};font-weight:500;font-size:${size}px;letter-spacing:${GL.TRACK};color:${rgb(GL.BRAND)};display:none`;
  b.textContent=word; p.appendChild(b);
  return {up:t=>t<tCut-0.44?0:-38*Math.pow(clamp((t-(tCut-0.44))/0.4),2),
    draw:(t,until=1e9)=>{ b.style.display=t>=tCut&&t<until?'block':'none'; if(t<tCut) return; const u=clamp((t-tCut)/0.5), e=1-Math.pow(1-u,3), s=scale(t);
      b.style.transform=`translate(-50%,0) translate(0,${540-14*s-0.62*size*s+26*(1-e)}px) scale(${s})`; }, el:b};
}

/* the blue: not a radial gradient. A saturated core, a lighter periwinkle band, and violet bands curving round the right side
   and lower left like a heavily blurred ring, lifting to lavender at the edges (colours sampled from the source's 5.5–9.2 s).
   Painted once with canvas blur filters, then only transformed. */
let MESH=null;
function meshURL(){ if(MESH) return MESH;
  const W=2400, H=1350, c=document.createElement('canvas'); c.width=W; c.height=H; const g=c.getContext('2d');
  const ox=(W-1920)/2, oy=(H-1080)/2;
  g.fillStyle='rgb(196,214,255)'; g.fillRect(0,0,W,H);
  const blob=(x,y,rx,ry,rot,col,blur)=>{ g.save(); g.filter=`blur(${blur}px)`; g.fillStyle=col; g.beginPath(); g.ellipse(ox+x,oy+y,rx,ry,rot,0,Math.PI*2); g.fill(); g.restore(); };
  const arc=(x,y,rx,ry,rot,a0,a1,w,col,blur)=>{ g.save(); g.filter=`blur(${blur}px)`; g.strokeStyle=col; g.lineWidth=w; g.lineCap='round'; g.beginPath(); g.ellipse(ox+x,oy+y,rx,ry,rot,a0,a1); g.stroke(); g.restore(); };
  blob(60,20,640,460,0,'rgb(226,236,255)',240); blob(1880,1080,640,440,0,'rgb(220,232,255)',240); blob(-80,640,380,700,0,'rgb(214,228,255)',220);
  arc(990,570,960,620,-0.22,-1.05,1.3,360,'rgb(52,108,255)',230);
  arc(990,570,960,620,-0.22,2.5,3.8,320,'rgb(70,124,255)',240);
  blob(960,555,700,440,-0.08,'rgb(120,166,255)',230);
  blob(960,550,470,290,-0.08,'rgb(64,128,255)',200);
  blob(960,1100,520,150,0,'rgb(90,145,255)',160);
  MESH=c.toDataURL('image/jpeg',0.95); return MESH; }

/* bloom(parent, t0): the soft ellipse grows from the centre (frames 126–136) and becomes the background (mesh) */
function bloom(p,t0){
  const m=document.createElement('img'); m.src=meshURL(); m.style.cssText='position:absolute;left:-240px;top:-135px;width:2400px;height:1350px;display:none';
  /* the bloom is the blue itself, seen through a very soft opening that grows (no flat ellipse of colour) */
  const e=document.createElement('div'); e.style.cssText='position:absolute;inset:0;display:none'; const ei=document.createElement('img'); ei.src=meshURL(); ei.style.cssText='position:absolute;left:-240px;top:-135px;width:2400px;height:1350px'; e.appendChild(ei);
  p.appendChild(m); p.appendChild(e);
  const R=GL.BLOOM_R, full=t0+fr(R.length);
  return t=>{ const f=(t-t0)*F;
    if(f<0){ e.style.display=m.style.display='none'; return; }
    m.style.display=f>=R.length-1?'block':'none';
    if(f>=R.length+1){ e.style.display='none'; } else { const r=f<R.length-1?lerp(R[Math.floor(f)],R[Math.min(R.length-1,Math.floor(f)+1)],f-Math.floor(f)):R.at(-1)*1.4;
      const a=r*Math.sqrt(GL.BLOOM_ASPECT)*1.25, b=r/Math.sqrt(GL.BLOOM_ASPECT)*1.25; e.style.display='block';
      const mk=`radial-gradient(${a.toFixed(0)}px ${b.toFixed(0)}px at 50% 50%, #000 0%, rgba(0,0,0,.92) 22%, rgba(0,0,0,.6) 48%, rgba(0,0,0,.22) 74%, rgba(0,0,0,0) 100%)`;
      e.style.webkitMaskImage=mk; e.style.maskImage=mk; e.style.filter=`blur(${(18*(1-f/R.length)).toFixed(1)}px) saturate(${(1.15-0.15*f/R.length).toFixed(2)})`; }
    const q=clamp((t-full)/4), e2=1-Math.pow(1-q,2); m.style.transform=`translate(${-36*e2}px,${12*e2}px) scale(${1+0.04*e2}) rotate(${-1.2*e2}deg)`; };
}

/* dotsToMark(parent, svgPathDs, place, t0, dots): the dots stand where the labels left them; from t0 white hairlines grow
   out of each dot along the mark's outline in both directions (ease in-out, staggered), then the mark turns to glass at tGlass. */
function dotsToMark(p,ds,{x,y,w,vb},t0,anchors,tGlass){
  const k=w/vb.w, NS='http://www.w3.org/2000/svg', svg=document.createElementNS(NS,'svg'); svg.setAttribute('width',1920); svg.setAttribute('height',1080);
  svg.style.cssText='position:absolute;left:0;top:0;overflow:visible;display:none';
  svg.innerHTML=`<defs><linearGradient id="glg" x1="0" y1="0" x2=".6" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".22"/><stop offset=".45" stop-color="#fff" stop-opacity=".05"/><stop offset="1" stop-color="#E9EEFF" stop-opacity=".14"/></linearGradient>
      <linearGradient id="glr" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fff" stop-opacity="1"/><stop offset=".5" stop-color="#fff" stop-opacity=".35"/><stop offset="1" stop-color="#fff" stop-opacity=".85"/></linearGradient>
      <filter id="glf" x="-20%" y="-20%" width="140%" height="140%" color-interpolation-filters="sRGB">
        <feComponentTransfer in="SourceAlpha" result="inv"><feFuncA type="table" tableValues="1 0"/></feComponentTransfer>
        <feGaussianBlur in="inv" stdDeviation="${7/k}" result="ib"/>
        <feOffset id="glo1" in="ib" dx="0" dy="0" result="io1"/><feFlood flood-color="#ffffff" flood-opacity=".95"/><feComposite in2="io1" operator="in" result="hi"/><feComposite in="hi" in2="SourceAlpha" operator="in" result="glow"/>
        <feGaussianBlur in="inv" stdDeviation="${12/k}" result="ib2"/>
        <feOffset id="glo2" in="ib2" dx="0" dy="0" result="io2"/><feFlood flood-color="#0B3FC9" flood-opacity=".45"/><feComposite in2="io2" operator="in" result="lo"/><feComposite in="lo" in2="SourceAlpha" operator="in" result="shade"/>
        <feFlood flood-color="#ffffff" flood-opacity=".16" result="body"/><feComposite in="body" in2="SourceAlpha" operator="in" result="bodyc"/>
        <feGaussianBlur in="SourceAlpha" stdDeviation="${14/k}" result="ds"/><feOffset in="ds" dy="${14/k}" result="dso"/><feFlood flood-color="#0B3FC9" flood-opacity=".14"/><feComposite in2="dso" operator="in" result="drop"/>
        <feMerge><feMergeNode in="drop"/><feMergeNode in="bodyc"/><feMergeNode in="shade"/><feMergeNode in="glow"/></feMerge></filter></defs>
    <g transform="translate(${x} ${y}) scale(${k}) translate(${-vb.x} ${-vb.y})">${ds.map(d=>`<path class="fill" d="${d}" fill="url(#glg)" fill-opacity="0" stroke="none" filter="url(#glf)"/>`).join('')}${anchors.map(a=>`<path class="ln" d="${ds[a.path]}" fill="none" stroke="#fff" stroke-opacity=".92" stroke-width="${1.6/k}" stroke-linecap="round" pathLength="1"/>`).join('')}</g><g id="glassg"><g transform="translate(${x} ${y}) scale(${k}) translate(${-vb.x} ${-vb.y})">${ds.map(d=>`<path class="fill2" d="${d}" fill="#fff" fill-opacity="0" stroke="none" filter="url(#glf)"/>`).join('')}${ds.map(d=>`<path class="rim" d="${d}" fill="none" stroke="url(#glr)" stroke-width="${2.2/k}" stroke-opacity="0"/>`).join('')}${ds.map(d=>`<path class="sweep" d="${d}" fill="none" stroke="#fff" stroke-width="${3.6/k}" stroke-linecap="round" pathLength="1" stroke-dasharray="0.18 0.82" stroke-opacity="0" style="filter:drop-shadow(0 0 ${3/k}px #fff)"/>`).join('')}</g></g>`;
  p.appendChild(svg);
  const lns=[...svg.querySelectorAll('.ln')], fills=[...svg.querySelectorAll('.fill2')], rims=[...svg.querySelectorAll('.rim')], sweep=[...svg.querySelectorAll('.sweep')], gl=svg.querySelector('#glassg');
  const beads=anchors.map(()=>{ const b=document.createElement('div'); b.style.cssText='position:absolute;width:10px;height:10px;margin:-5px 0 0 -5px;border-radius:50%;border:1.5px solid #fff;box-sizing:border-box;background:rgba(255,255,255,.3);display:none'; p.appendChild(b); return b; });
  const ease=u=>u<.5?4*u*u*u:1-Math.pow(-2*u+2,3)/2;
  return t=>{ const on=t>=t0-fr(10); svg.style.display=on?'block':'none';
    anchors.forEach((a,i)=>{ const st=t0+i*0.12, u=ease(clamp((t-st)/0.9)), h=a.span*u;
      lns[i].setAttribute('stroke-dasharray',`${2*h} ${1-2*h}`); lns[i].setAttribute('stroke-dashoffset',`${-(a.s-h)}`);
      beads[i].style.display=on?'block':'none'; beads[i].style.width=beads[i].style.height='14px'; beads[i].style.margin='-7px 0 0 -7px'; beads[i].style.borderWidth='2px'; beads[i].style.left=a.px+'px'; beads[i].style.top=a.py+'px'; });
    const on2=t>=tGlass; lns.forEach(l=>{ l.style.opacity=on2?0:1; }); beads.forEach(b=>{ b.style.opacity=on2?0:1; });
    gl.setAttribute('transform',`translate(960 540) scale(${on2?0.8:1}) translate(-960 -540)`);
    const u2=clamp((t-tGlass)/0.36); fills.forEach(f=>f.setAttribute('fill-opacity',on2?1:0)); rims.forEach(r=>r.setAttribute('stroke-opacity',on2?0.22:0));
    /* the light travels: the inner glow comes from a direction that turns slowly, the shade sits opposite */
    const ang=-2.3+1.1*clamp((t-tGlass)/2.0), R1=4.5/k, R2=6/k; const o1=svg.querySelector('#glo1'), o2=svg.querySelector('#glo2');
    o1.setAttribute('dx',(Math.cos(ang)*R1).toFixed(3)); o1.setAttribute('dy',(Math.sin(ang)*R1).toFixed(3)); o2.setAttribute('dx',(-Math.cos(ang)*R2).toFixed(3)); o2.setAttribute('dy',(-Math.sin(ang)*R2).toFixed(3));
    sweep.forEach(sw=>{ sw.setAttribute('stroke-opacity',on2?(1-u2)*0.95:0); sw.setAttribute('stroke-dashoffset',`${-(0.55+0.5*u2)}`); }); };
}

window.GlassLight={GL,F,fr,clamp,lerp,centredLine,labelField,labelField3D,lensLayer,lensAt,dot3D,dotAt,roll,bloom,dotsToMark,camera,SL,tab};
})();
