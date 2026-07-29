(function(){try{var e=typeof window<`u`?window:typeof global<`u`?global:typeof globalThis<`u`?globalThis:typeof self<`u`?self:{};e.SENTRY_RELEASE={id:`0077f92838c1ecce1c3ce71ae3d1ce1c9d2a4137`};var t=new e.Error().stack;t&&(e._sentryDebugIds=e._sentryDebugIds||{},e._sentryDebugIds[t]=`bb2b5891-845d-4bf8-be7f-e7ab1949579c`,e._sentryDebugIdIdentifier=`sentry-dbid-bb2b5891-845d-4bf8-be7f-e7ab1949579c`)}catch{}})();import{n as e}from"./rolldown-runtime-201nhtia.js";import{Pt as t,Xn as n,rr as r}from"./src-DMrNoiOy.js";import{n as i,t as a}from"./mermaid-parser.core-DZbpaKU0.js";import{g as o,h as s,m as c,t as l}from"./src-o3swA38F.js";import{U as u,W as d,a as f,c as p,f as m,j as h,q as g,v as _,w as v,x as y,y as b}from"./chunk-CSCIHK7Q-DIATZ9Yi.js";import{n as x,t as S}from"./chunk-WU5MYG2G-11arz9Av.js";import{d as C,i as w,m as T}from"./chunk-5ZQYHXKU-aKw-wgoL.js";import{n as E,t as D}from"./chunk-4BX2VUAB-qxq9mFsW.js";var O,k,A,j,M,N,P,F,I,L,R;e((()=>{S(),D(),C(),h(),s(),a(),l(),O=m.pie,k={sections:new Map,showData:!1,config:O},A=k.sections,j=k.showData,M=structuredClone(O),N={getConfig:c(()=>structuredClone(M),`getConfig`),clear:c(()=>{A=new Map,j=k.showData,f()},`clear`),setDiagramTitle:g,getDiagramTitle:v,setAccTitle:d,getAccTitle:b,setAccDescription:u,getAccDescription:_,addSection:c(({label:e,value:t})=>{if(t<0)throw Error(`"${e}" has invalid value: ${t}. Negative values are not allowed in pie charts. All slice values must be >= 0.`);A.has(e)||(A.set(e,t),o.debug(`added new section: ${e}, with value: ${t}`))},`addSection`),getSections:c(()=>A,`getSections`),setShowData:c(e=>{j=e},`setShowData`),getShowData:c(()=>j,`getShowData`)},P=c((e,t)=>{E(e,t),t.setShowData(e.showData),e.sections.map(t.addSection)},`populateDb`),F={parse:c(async e=>{let t=await i(`pie`,e);o.debug(t),P(t,N)},`parse`)},I=c(e=>`
  .pieCircle{
    stroke: ${e.pieStrokeColor};
    stroke-width : ${e.pieStrokeWidth};
    opacity : ${e.pieOpacity};
  }
  .pieOuterCircle{
    stroke: ${e.pieOuterStrokeColor};
    stroke-width: ${e.pieOuterStrokeWidth};
    fill: none;
  }
  .pieTitleText {
    text-anchor: middle;
    font-size: ${e.pieTitleTextSize};
    fill: ${e.pieTitleTextColor};
    font-family: ${e.fontFamily};
  }
  .slice {
    font-family: ${e.fontFamily};
    fill: ${e.pieSectionTextColor};
    font-size:${e.pieSectionTextSize};
    // fill: white;
  }
  .legend text {
    fill: ${e.pieLegendTextColor};
    font-family: ${e.fontFamily};
    font-size: ${e.pieLegendTextSize};
  }
`,`getStyles`),L=c(e=>{let t=[...e.values()].reduce((e,t)=>e+t,0),r=[...e.entries()].map(([e,t])=>({label:e,value:t})).filter(e=>e.value/t*100>=1);return n().value(e=>e.value).sort(null)(r)},`createPieArcs`),R={parser:F,db:N,renderer:{draw:c((e,n,i,a)=>{o.debug(`rendering pie chart
`+e);let s=a.db,c=y(),l=w(s.getConfig(),c.pie),u=x(n),d=u.append(`g`);d.attr(`transform`,`translate(225,225)`);let{themeVariables:f}=c,[m]=T(f.pieOuterStrokeWidth);m??=2;let h=l.textPosition,g=r().innerRadius(0).outerRadius(185),_=r().innerRadius(185*h).outerRadius(185*h);d.append(`circle`).attr(`cx`,0).attr(`cy`,0).attr(`r`,185+m/2).attr(`class`,`pieOuterCircle`);let v=s.getSections(),b=L(v),S=[f.pie1,f.pie2,f.pie3,f.pie4,f.pie5,f.pie6,f.pie7,f.pie8,f.pie9,f.pie10,f.pie11,f.pie12],C=0;v.forEach(e=>{C+=e});let E=b.filter(e=>(e.data.value/C*100).toFixed(0)!==`0`),D=t(S).domain([...v.keys()]);d.selectAll(`mySlices`).data(E).enter().append(`path`).attr(`d`,g).attr(`fill`,e=>D(e.data.label)).attr(`class`,`pieCircle`),d.selectAll(`mySlices`).data(E).enter().append(`text`).text(e=>(e.data.value/C*100).toFixed(0)+`%`).attr(`transform`,e=>`translate(`+_.centroid(e)+`)`).style(`text-anchor`,`middle`).attr(`class`,`slice`);let O=d.append(`text`).text(s.getDiagramTitle()).attr(`x`,0).attr(`y`,-400/2).attr(`class`,`pieTitleText`),k=[...v.entries()].map(([e,t])=>({label:e,value:t})),A=d.selectAll(`.legend`).data(k).enter().append(`g`).attr(`class`,`legend`).attr(`transform`,(e,t)=>{let n=22*k.length/2;return`translate(216,`+(t*22-n)+`)`});A.append(`rect`).attr(`width`,18).attr(`height`,18).style(`fill`,e=>D(e.label)).style(`stroke`,e=>D(e.label)),A.append(`text`).attr(`x`,22).attr(`y`,14).text(e=>s.getShowData()?`${e.label} [${e.value}]`:e.label);let j=512+Math.max(...A.selectAll(`text`).nodes().map(e=>e?.getBoundingClientRect().width??0)),M=O.node()?.getBoundingClientRect().width??0,N=450/2-M/2,P=450/2+M/2,F=Math.min(0,N),I=Math.max(j,P)-F;u.attr(`viewBox`,`${F} 0 ${I} 450`),p(u,450,I,l.useMaxWidth)},`draw`)},styles:I}}))();export{R as diagram};