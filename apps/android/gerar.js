// Gera o projeto Android (Trusted Web Activity: o sistema abre em tela cheia usando o Chrome do aparelho).
// Uso: node gerar.js <numero-da-versao>
const {TwaManifest,TwaGenerator,ConsoleLog}=require('@bubblewrap/core');
const URL_SITE='https://pronutre-erp.web.app/';
(async()=>{const n=parseInt(process.argv[2]||'1',10);
  const mUrl=new URL('manifest.webmanifest',URL_SITE);let web;
  // o site pode estar sendo publicado junto: espera o manifesto com o ícone novo (até ~10 min)
  for(let i=0;i<40;i++){try{web=await (await fetch(mUrl,{cache:'no-store'})).json()}catch(e){web={}}if((web.icons||[]).some(x=>x.purpose==='maskable'))break;console.log('aguardando o site publicar o manifesto novo…');await new Promise(r=>setTimeout(r,15000))}
  const m=TwaManifest.fromWebManifestJson(mUrl,web);
  Object.assign(m,{packageId:'br.com.pronutre.erp',name:'Pronutre · Gestão de Negócios',launcherName:'Pronutre',appVersionCode:n,appVersionName:'1.0.'+n,
    signingKey:{path:require('path').join(__dirname,'pronutre.keystore'),alias:'pronutre'},enableNotifications:false,fallbackType:'customtabs',orientation:'default',enableSiteSettingsShortcut:false,minSdkVersion:24});
  console.log('versão',m.appVersionName,'pacote',m.packageId,'site',m.host);
  await new TwaGenerator().createTwaProject(require('path').join(__dirname,'twa'),m,new ConsoleLog('twa'));
  require('fs').writeFileSync(require('path').join(__dirname,'twa','twa-manifest.json'),JSON.stringify(m.toJson(),null,2));
})().catch(e=>{console.error(e);process.exit(1)});
