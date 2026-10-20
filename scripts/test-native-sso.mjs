import test from 'node:test';
import assert from 'node:assert/strict';
import {generateKeyPairSync,sign,createHash} from 'node:crypto';
import {writeFileSync,unlinkSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {installDevAntiq} from '../infrastructure/members/adapters/connector.mjs';
import {validateConfig,cookieValue,sessionBinding,PendingLogins,currentMembership,completePage} from '../infrastructure/members/adapters/connector.mjs';

test('OIDC client configuration fixes issuer and exact HTTPS callback', () => {
  const config = {issuer:'https://devantiq.com/auth/oidc',client_id:'client',client_secret:'x'.repeat(48),
    redirect_uri:'https://g1crm.devantiq.com/api/auth/sso/callback'};
  validateConfig('g1crm',config);
  for (const change of [{issuer:'https://evil.test'}, {redirect_uri:config.redirect_uri+'?next=evil'},
                       {client_secret:''}, {redirect_uri:config.redirect_uri.replace('https','http')}]) {
    assert.throws(() => validateConfig('g1crm',{...config,...change}));
  }
});

test('pending login is browser-bound by opaque ID, expires and is single-use', () => {
  let now = 0; const pending = new PendingLogins(() => now);
  const id = pending.add({nonce:'n'});
  assert.equal(pending.take('wrong'),null);
  assert.equal(pending.take(id).nonce,'n');
  assert.equal(pending.take(id),null);
  const expired = pending.add({nonce:'other'}); now=300001;
  assert.equal(pending.take(expired),null);
});

test('ambiguous cookies are rejected and only member cookie is forwarded', async () => {
  assert.equal(cookieValue('a=1; a=2','a'),'');
  let called=false;
  const member=await currentMembership('g1crm','other=secret; devantiq_member_session=abc123',async(url,options)=>{
    called=true;
    assert.equal(url,'https://devantiq.com/auth/apps/g1crm/session/');
    assert.equal(options.headers.Cookie,'devantiq_member_session=abc123');
    assert.equal(options.redirect,'error');
    return {ok:true,json:async()=>({sub:'9',external_account:'dedicated'})};
  });
  assert.equal(called,true); assert.equal(member.sub,'9');
  await assert.rejects(currentMembership('g1crm','',()=>{throw new Error('must not fetch')}));
  await assert.rejects(currentMembership('g1crm','devantiq_member_session=abc',async()=>({ok:false})));
});

test('native token binding cannot silently omit a partial SSO identity',()=>{
  const token=body=>'header.'+Buffer.from(JSON.stringify(body)).toString('base64url')+'.signature';
  assert.equal(sessionBinding(token({sub:'native'})),null);
  assert.deepEqual(sessionBinding(token({devantiq_sub:'9',devantiq_account:'dedicated'})),{sub:'9',external_account:'dedicated'});
  assert.equal(sessionBinding(token({devantiq_sub:'9'})).invalid,true);
});

test('session handoff keeps tokens out of URLs and escapes script injection',()=>{
  const page=completePage({token:'</script><script>alert(1)</script>'});
  assert.equal((page.html.match(/<script/g)||[]).length,1);
  assert.ok(page.html.includes("location.replace('/')"));
  assert.ok(page.html.includes('\\u003c/script>'));
  assert.ok(page.nonce.length>=32);
  assert.ok(completePage({g1crm_token:'test'},'g1crm').html.includes("location.replace('/dashboard')"));
  assert.ok(completePage({},'https://untrusted.example').html.includes("location.replace('/')"));
});

test('real OIDC library validates code, PKCE, nonce, signature and blocks cross-member native reuse',async()=>{
  const issuer='https://devantiq.com/auth/oidc';
  const {privateKey,publicKey}=generateKeyPairSync('rsa',{modulusLength:2048});
  const jwk={...publicKey.export({format:'jwk'}),kid:'test',alg:'RS256',use:'sig'};
  const routes=new Map();
  const app={get:(path,...handlers)=>routes.set('GET '+path,handlers.at(-1)),
    post:(path,...handlers)=>routes.set('POST '+path,handlers.at(-1)),
    use:(path,handler)=>routes.set('USE '+path,handler)};
  const response=()=>({headers:{},statusCode:200,set(key,value){this.headers[key]=value;return this;},
    status(code){this.statusCode=code;return this;},type(){return this;},
    send(body){this.body=body;return this;},json(body){this.body=body;return this;},
    redirect(url){this.location=url;return this;}});
  const filename=fileURLToPath(new URL('../.vps-inspection/test-oidc-client.json',import.meta.url));
  writeFileSync(filename,JSON.stringify({issuer,client_id:'client',client_secret:'x'.repeat(48),
    redirect_uri:'https://g1crm.devantiq.com/api/auth/sso/callback'}));
  let authUrl, subject='9', issued=0, wrongNonce=false, needsMfa=false;
  const json=body=>new Response(JSON.stringify(body),{headers:{'content-type':'application/json'}});
  const membershipFetch=async()=>({ok:true,json:async()=>({sub:subject,external_account:'dedicated'})});
  try {
    installDevAntiq(app,{appId:'g1crm',configPath:filename,parseForm:()=>{},membershipFetch,
      resolveIdentity:async()=>({verifyMfa:needsMfa ? code=>code==='123456' : undefined,
        issueSession:()=>{issued++; return {token:'native-session'};}}),
      protocolFetch:async(url,options)=>{
        const path=new URL(url).pathname;
        if(path.endsWith('/jwks.json')) return json({keys:[jwk]});
        if(path.endsWith('/userinfo/')) return json({sub:'9',external_account:'dedicated'});
        assert.ok(path.endsWith('/token/'));
        const params=new URLSearchParams(options.body);
        assert.equal(params.get('code'),'valid-code');
        assert.equal(createHash('sha256').update(params.get('code_verifier')).digest('base64url'),authUrl.searchParams.get('code_challenge'));
        const encode=value=>Buffer.from(JSON.stringify(value)).toString('base64url');
        const jwt=encode({alg:'RS256',kid:'test'})+'.'+encode({iss:issuer,aud:'client',sub:'9',
          iat:Math.floor(Date.now()/1000),exp:Math.floor(Date.now()/1000)+300,
          nonce:wrongNonce ? 'wrong-nonce' : authUrl.searchParams.get('nonce'),external_account:'dedicated'});
        return json({access_token:'access',token_type:'Bearer',expires_in:300,
          id_token:jwt+'.'+sign('RSA-SHA256',Buffer.from(jwt),privateKey).toString('base64url')});
      }});
    const start=response();
    await routes.get('GET /api/auth/sso/login')({headers:{cookie:'devantiq_member_session=abc123'}},start);
    authUrl=new URL(start.location);
    const cookie=start.headers['Set-Cookie'].split(';')[0]+'; devantiq_member_session=abc123';
    const request={headers:{cookie},originalUrl:'/api/auth/sso/callback?code=valid-code&state='+authUrl.searchParams.get('state')};
    const done=response(); await routes.get('GET /api/auth/sso/callback')(request,done);
    assert.equal(done.statusCode,200,done.body);
    assert.equal(issued,1);
    const replay=response(); await routes.get('GET /api/auth/sso/callback')(request,replay);
    assert.equal(replay.statusCode,403); assert.equal(issued,1);
    subject='another-member';
    const token='header.'+Buffer.from(JSON.stringify({devantiq_sub:'9',devantiq_account:'dedicated'})).toString('base64url')+'.signature';
    const denied=response();
    await routes.get('USE /api')({headers:{authorization:'Bearer '+token,cookie:'devantiq_member_session=abc123'}},denied,()=>assert.fail('must refuse'));
    assert.equal(denied.statusCode,401);
    subject='9'; wrongNonce=true;
    const again=response();
    await routes.get('GET /api/auth/sso/login')({headers:{cookie:'devantiq_member_session=abc123'}},again);
    authUrl=new URL(again.location);
    const bad=response();
    await routes.get('GET /api/auth/sso/callback')({headers:{cookie:again.headers['Set-Cookie'].split(';')[0]+'; devantiq_member_session=abc123'},
      originalUrl:'/api/auth/sso/callback?code=valid-code&state='+authUrl.searchParams.get('state')},bad);
    assert.equal(bad.statusCode,403); assert.equal(issued,1);
    wrongNonce=false; needsMfa=true;
    const mfaStart=response();
    await routes.get('GET /api/auth/sso/login')({headers:{cookie:'devantiq_member_session=abc123'}},mfaStart);
    authUrl=new URL(mfaStart.location);
    const form=response();
    await routes.get('GET /api/auth/sso/callback')({headers:{cookie:mfaStart.headers['Set-Cookie'].split(';')[0]+'; devantiq_member_session=abc123'},
      originalUrl:'/api/auth/sso/callback?code=valid-code&state='+authUrl.searchParams.get('state')},form);
    assert.equal(form.statusCode,200); assert.equal(issued,1);
    assert.ok(form.body.includes('Double authentification'));
    const mfaDone=response();
    await routes.get('POST /api/auth/sso/mfa')({headers:{cookie:form.headers['Set-Cookie'].split(';')[0]+'; devantiq_member_session=abc123',origin:'https://g1crm.devantiq.com'},
      body:{csrf:form.body.match(/name="csrf" value="([^"]+)"/)[1],code:'123456'}},mfaDone);
    assert.equal(mfaDone.statusCode,200); assert.equal(issued,2);
  } finally {unlinkSync(filename);}
});
