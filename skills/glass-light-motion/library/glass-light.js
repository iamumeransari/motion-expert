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
  PRE:[207,222,244],   // arrival frame (word at partial opacity, palest periwinkle)
  P0:[161,174,231],    // first full frame
  FADE:[156,167,205],  // a trimmed word's colour on its last frame
  BRAND:[141,158,242], // the brand word
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
      w.style.color=rgb(c); });
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
    d.innerHTML=`<span style="color:rgb(31,32,35)">${o.n}</span><span style="width:8px;height:8px;border-radius:50%;background:rgb(167,169,233);box-shadow:0 0 0 3px rgba(255,255,255,.9),0 1px 4px rgba(120,130,200,.35);margin:0 18px;flex:none"></span><span style="color:rgb(163,172,230)">${o.v}</span>`;
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
function labelField3D(p,front,t0,{nameOff=null,size=41,mid=[],back=[],dotsUntil=1e9,roll=[-3,1.5]}={}){
  const Zf=640, F=295.3, c=t=>Zf-F/tab(SL,t-t0);
  const mk=(o,i,Z,kind)=>{ const d=document.createElement('div');
    d.style.cssText=`position:absolute;left:0;top:0;white-space:nowrap;font-family:${GL.FONT};font-weight:500;font-size:${size}px;letter-spacing:-0.01em;display:flex;align-items:center;transform-origin:0 50%`;
    d.innerHTML=`<span style="color:rgb(31,32,35)">${o.n}</span><span style="width:8px;height:8px;border-radius:50%;background:rgb(167,169,233);box-shadow:0 0 0 3px rgba(255,255,255,.9),0 1px 4px rgba(120,130,200,.35);margin:0 18px;flex:none"></span><span style="color:rgb(163,172,230)">${o.v}</span>`;
    p.appendChild(d); const X=(o.x-960)*(Z-(Zf-F))/F, Y=(o.y-540)*(Z-(Zf-F))/F; return {d,o,i,Z,X,Y,kind}; };
  const N=[...front.map((o,i)=>mk(o,i,Zf,'front')),...mid.map((o,i)=>mk(o,i,1150,'mid')),...back.map((o,i)=>mk(o,i,1800,'back'))];
  const order=nameOff||front.map((_,i)=>i);
  return t=>{ const cz=c(t), u=clamp((t-t0)/2.2), th=(roll[0]+(roll[1]-roll[0])*u)*Math.PI/180, co=Math.cos(th), si=Math.sin(th);
    for(const q of N){ const {d,o,i,Z,kind}=q;
      if(t<t0||t>=dotsUntil){ d.style.display='none'; continue; } d.style.display='flex';
      const s=F/(Z-cz); const X=q.X*co-q.Y*si, Y=q.X*si+q.Y*co; const sx=960+X*s/((Z-(Zf-F))/F)*((Z-(Zf-F))/F), sy=540+Y*s;
      const px=960+X*s, py=540+Y*s;
      const sf=tab(SL,t-t0), far=clamp((1-sf)/0.45), on=clamp((t-t0-0.012*i-(kind==='front'?0:kind==='mid'?-0.1:-0.2))/0.3);
      d.style.transform=`translate(${px}px,${py}px) translateY(-50%) scale(${kind==='mid'?-s:s},${s}) rotate(${(o.rot||0)+th*57.3}deg)`;
      const [n,dot,v]=d.children;
      if(kind==='front'){ const k=order.indexOf(i), off=t0+1.16+k*fr(1.6), nOut=t>=off?1:0, vOut=clamp((t-off-fr(2))/fr(8));
        d.style.opacity=on.toFixed(3); d.style.filter=`blur(${(far*4).toFixed(2)}px)`;
        n.style.color=rgb(mixc([31,32,35],[178,188,236],far)); n.style.opacity=1-nOut; v.style.opacity=1-vOut; dot.style.opacity=o.keepDot?1:1-vOut; }
      else { const fade=1-clamp((t-t0-1.0)/0.4), b=kind==='mid'?6:11, a=kind==='mid'?0.42:0.22;
        d.style.opacity=(on*a*fade).toFixed(3); d.style.filter=`blur(${b}px)`; n.style.color=rgb([150,160,205]); } }
  };
}
/* where a front label's dot is on screen at time t (rolled), for handing dots to the mark */
function dot3D(o,nameW,t,t0,roll=[-3,1.5]){ const Zf=640,F=295.3, cz=Zf-F/tab(SL,t-t0), s=F/(Zf-cz), u=clamp((t-t0)/2.2), th=(roll[0]+(roll[1]-roll[0])*u)*Math.PI/180;
  const X=(o.x+nameW+22-960), Y=(o.y-540); return {x:960+(X*Math.cos(th)-Y*Math.sin(th))*s, y:540+(X*Math.sin(th)+Y*Math.cos(th))*s}; }

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
  g.fillStyle='rgb(184,197,252)'; g.fillRect(0,0,W,H);
  const blob=(x,y,rx,ry,rot,col,blur)=>{ g.save(); g.filter=`blur(${blur}px)`; g.fillStyle=col; g.beginPath(); g.ellipse(ox+x,oy+y,rx,ry,rot,0,Math.PI*2); g.fill(); g.restore(); };
  const arc=(x,y,rx,ry,rot,a0,a1,w,col,blur)=>{ g.save(); g.filter=`blur(${blur}px)`; g.strokeStyle=col; g.lineWidth=w; g.lineCap='round'; g.beginPath(); g.ellipse(ox+x,oy+y,rx,ry,rot,a0,a1); g.stroke(); g.restore(); };
  blob(80,40,520,380,0,'rgb(214,220,254)',160); blob(1850,1060,520,360,0,'rgb(208,214,253)',160); blob(-60,620,300,600,0,'rgb(200,210,253)',150);
  arc(980,560,930,600,-0.2,-1.0,1.25,300,'rgb(156,150,246)',130);
  arc(980,560,930,600,-0.2,2.55,3.75,260,'rgb(162,158,247)',140);
  arc(960,560,640,410,-0.1,0,Math.PI*2,150,'rgb(168,188,252)',90);
  blob(960,555,560,350,-0.08,'rgb(136,164,250)',150);
  blob(960,1080,420,120,0,'rgb(140,170,240)',90);
  MESH=c.toDataURL('image/jpeg',0.95); return MESH; }

/* bloom(parent, t0): the soft ellipse grows from the centre (frames 126–136) and becomes the background (mesh) */
function bloom(p,t0){
  const m=document.createElement('img'); m.src=meshURL(); m.style.cssText='position:absolute;left:-240px;top:-135px;width:2400px;height:1350px;display:none';
  const e=document.createElement('div'); e.style.cssText='position:absolute;left:960px;top:540px;border-radius:50%;display:none;background:radial-gradient(closest-side, rgb(138,167,250) 0%, rgb(138,167,250) 30%, rgba(150,176,250,.55) 62%, rgba(170,190,251,.18) 84%, rgba(190,204,252,0) 100%)';
  p.appendChild(m); p.appendChild(e);
  const R=GL.BLOOM_R, full=t0+fr(R.length);
  return t=>{ const f=(t-t0)*F;
    if(f<0){ e.style.display=m.style.display='none'; return; }
    m.style.display=f>=R.length-1?'block':'none';
    if(f>=R.length+1){ e.style.display='none'; } else { const r=f<R.length-1?lerp(R[Math.floor(f)],R[Math.min(R.length-1,Math.floor(f)+1)],f-Math.floor(f)):R.at(-1)*1.4;
      const a=r*Math.sqrt(GL.BLOOM_ASPECT), b=r/Math.sqrt(GL.BLOOM_ASPECT); e.style.display='block';
      e.style.width=2*a+'px'; e.style.height=2*b+'px'; e.style.marginLeft=-a+'px'; e.style.marginTop=-b+'px'; }
    const q=clamp((t-full)/4), e2=1-Math.pow(1-q,2); m.style.transform=`translate(${-36*e2}px,${12*e2}px) scale(${1+0.04*e2}) rotate(${-1.2*e2}deg)`; };
}

/* dotsToMark(parent, svgPathDs, place, t0, dots): the dots stand where the labels left them; from t0 white hairlines grow
   out of each dot along the mark's outline in both directions (ease in-out, staggered), then the mark turns to glass at tGlass. */
function dotsToMark(p,ds,{x,y,w,vb},t0,anchors,tGlass){
  const k=w/vb.w, NS='http://www.w3.org/2000/svg', svg=document.createElementNS(NS,'svg'); svg.setAttribute('width',1920); svg.setAttribute('height',1080);
  svg.style.cssText='position:absolute;left:0;top:0;overflow:visible;display:none';
  svg.innerHTML=`<defs><linearGradient id="glg" x1="0" y1="0" x2=".6" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".62"/><stop offset=".45" stop-color="#fff" stop-opacity=".18"/><stop offset="1" stop-color="#E9EEFF" stop-opacity=".38"/></linearGradient>
      <linearGradient id="glr" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#fff" stop-opacity="1"/><stop offset=".5" stop-color="#fff" stop-opacity=".35"/><stop offset="1" stop-color="#fff" stop-opacity=".85"/></linearGradient>
      <filter id="glf" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur in="SourceAlpha" stdDeviation="${6/k}" result="b"/><feOffset dy="${10/k}" result="o"/><feFlood flood-color="#5468D8" flood-opacity=".28"/><feComposite in2="o" operator="in" result="sh"/><feMerge><feMergeNode in="sh"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>
    <g transform="translate(${x} ${y}) scale(${k}) translate(${-vb.x} ${-vb.y})">${ds.map(d=>`<path class="fill" d="${d}" fill="url(#glg)" fill-opacity="0" stroke="none" filter="url(#glf)"/>`).join('')}${anchors.map(a=>`<path class="ln" d="${ds[a.path]}" fill="none" stroke="#fff" stroke-opacity=".92" stroke-width="${1.6/k}" stroke-linecap="round" pathLength="1"/>`).join('')}${ds.map(d=>`<path class="rim" d="${d}" fill="none" stroke="url(#glr)" stroke-width="${2.6/k}" stroke-opacity="0"/>`).join('')}</g>`;
  p.appendChild(svg);
  const lns=[...svg.querySelectorAll('.ln')], fills=[...svg.querySelectorAll('.fill')], rims=[...svg.querySelectorAll('.rim')];
  const beads=anchors.map(()=>{ const b=document.createElement('div'); b.style.cssText='position:absolute;width:10px;height:10px;margin:-5px 0 0 -5px;border-radius:50%;border:1.5px solid #fff;box-sizing:border-box;background:rgba(255,255,255,.3);display:none'; p.appendChild(b); return b; });
  const ease=u=>u<.5?4*u*u*u:1-Math.pow(-2*u+2,3)/2;
  return t=>{ const on=t>=t0-fr(10); svg.style.display=on?'block':'none';
    anchors.forEach((a,i)=>{ const st=t0+i*0.12, u=ease(clamp((t-st)/1.5)), h=a.span*u;
      lns[i].setAttribute('stroke-dasharray',`${2*h} ${1-2*h}`); lns[i].setAttribute('stroke-dashoffset',`${-(a.s-h)}`);
      lns[i].style.opacity=t<tGlass?1:1-clamp((t-tGlass)/0.25);
      beads[i].style.display=on?'block':'none'; beads[i].style.width=beads[i].style.height='14px'; beads[i].style.margin='-7px 0 0 -7px'; beads[i].style.borderWidth='2px'; beads[i].style.left=a.px+'px'; beads[i].style.top=a.py+'px'; beads[i].style.opacity=1-clamp((t-tGlass)/0.2); });
    const g=clamp((t-tGlass)/0.35); fills.forEach(f=>f.setAttribute('fill-opacity',g)); rims.forEach(r=>r.setAttribute('stroke-opacity',g)); };
}

window.GlassLight={GL,F,fr,clamp,lerp,centredLine,labelField,labelField3D,dot3D,dotAt,roll,bloom,dotsToMark,camera,SL,tab};
})();
