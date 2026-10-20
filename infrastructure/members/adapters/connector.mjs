import * as oidc from 'openid-client';
import { randomBytes } from 'node:crypto';
import { readFileSync } from 'node:fs';

const ISSUER = 'https://devantiq.com/auth/oidc';
const BASE = '/api/auth/sso';
const COOKIE = '__Host-devantiq_sso';
const random = () => randomBytes(32).toString('base64url');
const jsonForHtml = value => JSON.stringify(value).replace(/</g, '\\u003c');

export function validateConfig(appId, value) {
  if (!/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(appId)
      || value.issuer !== ISSUER || typeof value.client_id !== 'string' || !value.client_id
      || typeof value.client_secret !== 'string' || value.client_secret.length < 32
      || value.redirect_uri !== `https://${appId}.devantiq.com${BASE}/callback`) {
    throw new Error('Invalid DevAntiq client configuration');
  }
  return value;
}

export function cookieValue(header, name) {
  const values = String(header || '').split(';').map(part => part.trim())
    .filter(part => part.startsWith(name + '='));
  return values.length === 1 ? values[0].slice(name.length + 1) : '';
}

// These unverified fields may only impose additional denial checks. The native
// application still verifies its own signature and account before allowing use.
export function sessionBinding(token) {
  try {
    const body = JSON.parse(Buffer.from(String(token).split('.')[1], 'base64url').toString());
    if (!Object.hasOwn(body, 'devantiq_sub')) return null;
    if (typeof body.devantiq_sub !== 'string' || !body.devantiq_sub
        || typeof body.devantiq_account !== 'string' || !body.devantiq_account) throw new Error();
    return { sub: body.devantiq_sub, external_account: body.devantiq_account };
  } catch { return { invalid: true }; }
}

export class PendingLogins {
  constructor(now = Date.now) { this.records = new Map(); this.now = now; }
  add(value) {
    for (const [id, record] of this.records) if (record.expires <= this.now()) this.records.delete(id);
    if (this.records.size >= 1024) throw new Error('Too many pending logins');
    const id = random();
    this.records.set(id, { ...value, expires: this.now() + 300000 });
    return id;
  }
  take(id) {
    const value = this.records.get(id);
    this.records.delete(id);
    return value && value.expires > this.now() ? value : null;
  }
}

export async function currentMembership(appId, cookie, fetcher = fetch) {
  const session = cookieValue(cookie, 'devantiq_member_session');
  if (!/^[a-zA-Z0-9]+$/.test(session)) throw new Error('Missing member session');
  const response = await fetcher(`https://devantiq.com/auth/apps/${appId}/session/`, {
    headers: { Cookie: `devantiq_member_session=${session}` },
    redirect: 'error', signal: AbortSignal.timeout(8000), cache: 'no-store',
  });
  if (!response.ok) throw new Error('Membership denied');
  const value = await response.json();
  if (typeof value.sub !== 'string' || typeof value.external_account !== 'string'
      || !value.sub || !value.external_account) throw new Error('Invalid member session');
  return value;
}

export async function guardWebSocket(appId, ws, req, nativeToken = null) {
  const binding = nativeToken ? sessionBinding(nativeToken) : null;
  const check = async () => {
    if (nativeToken) {
      const payload = JSON.parse(Buffer.from(nativeToken.split('.')[1], 'base64url').toString());
      if (typeof payload.exp !== 'number' || payload.exp <= Date.now()/1000) throw new Error('Expired WebSocket token');
    }
    const member = await currentMembership(appId, req.headers.cookie);
    if (binding && (binding.invalid || member.sub !== binding.sub || member.external_account !== binding.external_account))
      throw new Error('WebSocket identity changed');
  };
  try { await check(); } catch { ws.close(4001, 'DevAntiq session required'); return false; }
  if (ws.readyState !== 1) return false;
  ws._devantiqVerified = true;
  const timer = setInterval(() => {
    check().catch(() => { ws._devantiqVerified = false; ws.close(4001, 'DevAntiq session expired'); });
  }, 15000);
  timer.unref();
  ws.once('close', () => clearInterval(timer));
  return true;
}

function headers(res) {
  res.set('Cache-Control', 'no-store');
  res.set('Referrer-Policy', 'no-referrer');
  res.set('X-Frame-Options', 'DENY');
  res.set('X-Content-Type-Options', 'nosniff');
}

export function completePage(storage, appId) {
  const nonce = random();
  const destination = appId === 'g1crm' ? '/dashboard' : '/';
  const script = `const values=${jsonForHtml(storage)}; for(const [key,value] of Object.entries(values)){if(value===null)localStorage.removeItem(key);else localStorage.setItem(key,String(value));} location.replace('${destination}');`;
  return { nonce, html: `<!doctype html><html lang="fr"><meta charset="utf-8"><title>Connexion DevAntiq</title><p>Connexion réussie. Ouverture de l’application…</p><script nonce="${nonce}">${script}</script></html>` };
}

/** resolveIdentity(claims) returns {issueSession(), verifyMfa?(code)}.
 * It must resolve an explicitly associated local account, preserve its role,
 * check its active status and attach devantiq_sub/account to native tokens.
 */
export function installDevAntiq(app, { appId, configPath, resolveIdentity, parseForm,
    protocolFetch, membershipFetch = fetch }) {
  const credentials = validateConfig(appId, JSON.parse(readFileSync(configPath, 'utf8')));
  const origin = `https://${appId}.devantiq.com`;
  const config = new oidc.Configuration({ issuer: ISSUER,
    authorization_endpoint: ISSUER + '/authorize/', token_endpoint: ISSUER + '/token/',
    userinfo_endpoint: ISSUER + '/userinfo/', jwks_uri: ISSUER + '/.well-known/jwks.json',
    id_token_signing_alg_values_supported: ['RS256'],
  }, credentials.client_id, { client_secret: credentials.client_secret,
    id_token_signed_response_alg: 'RS256' }, oidc.ClientSecretPost(credentials.client_secret));
  oidc.enableNonRepudiationChecks(config);
  if (protocolFetch) config[oidc.customFetch] = protocolFetch;
  const pending = new PendingLogins();
  const setCookie = (res, id) => res.set('Set-Cookie', `${COOKIE}=${id}; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=${id ? 300 : 0}`);
  const wrapper = handler => async (req, res) => {
    headers(res);
    try { await handler(req, res); }
    catch { setCookie(res, ''); res.status(403).send('Connexion DevAntiq refusée ou expirée. Revenez dans votre espace membres et réessayez.'); }
  };
  const checkMember = async (req, claims) => {
    const member = await currentMembership(appId, req.headers.cookie, membershipFetch);
    if (member.sub !== claims.sub || member.external_account !== claims.external_account) throw new Error('Account changed');
  };
  const finish = async (req, res, claims) => {
    await checkMember(req, claims);
    const identity = await resolveIdentity(claims);
    const storage = await identity.issueSession();
    const page = completePage(storage, appId);
    setCookie(res, '');
    res.set('Content-Security-Policy', `default-src 'none'; script-src 'nonce-${page.nonce}'; base-uri 'none'; frame-ancestors 'none'`);
    res.type('html').send(page.html);
  };

  app.get(BASE + '/login', wrapper(async (req, res) => {
    const member = await currentMembership(appId, req.headers.cookie, membershipFetch);
    const verifier = oidc.randomPKCECodeVerifier(), state = oidc.randomState(), nonce = oidc.randomNonce();
    const id = pending.add({ verifier, state, nonce, member });
    setCookie(res, id);
    const url = oidc.buildAuthorizationUrl(config, { redirect_uri: credentials.redirect_uri,
      scope: 'openid profile', state, nonce, code_challenge_method: 'S256',
      code_challenge: await oidc.calculatePKCECodeChallenge(verifier) });
    res.redirect(url.href);
  }));

  app.get(BASE + '/callback', wrapper(async (req, res) => {
    const flow = pending.take(cookieValue(req.headers.cookie, COOKIE));
    if (!flow || !flow.verifier) throw new Error('Expired state');
    const url = new URL(credentials.redirect_uri);
    url.search = new URL(req.originalUrl, origin).search;
    const tokens = await oidc.authorizationCodeGrant(config, url, {
      pkceCodeVerifier: flow.verifier, expectedState: flow.state, expectedNonce: flow.nonce,
      idTokenExpected: true,
    });
    const claims = tokens.claims();
    const info = await oidc.fetchUserInfo(config, tokens.access_token, claims.sub);
    if (info.sub !== flow.member.sub || info.external_account !== flow.member.external_account
        || claims.external_account !== info.external_account) throw new Error('Identity mismatch');
    await checkMember(req, info);
    const identity = await resolveIdentity(info);
    if (identity.verifyMfa) {
      const csrf = random();
      setCookie(res, pending.add({ claims: info, csrf }));
      res.set('Content-Security-Policy', "default-src 'none'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'");
      return res.type('html').send(`<!doctype html><html lang="fr"><meta charset="utf-8"><title>Double authentification</title><h1>Code de double authentification</h1><form method="post" action="${BASE}/mfa"><input type="hidden" name="csrf" value="${csrf}"><input name="code" inputmode="numeric" pattern="[0-9]{6}" autocomplete="one-time-code" required autofocus><button>Se connecter</button></form></html>`);
    }
    await finish(req, res, info);
  }));

  app.post(BASE + '/mfa', parseForm, wrapper(async (req, res) => {
    const flow = pending.take(cookieValue(req.headers.cookie, COOKIE));
    if (!flow?.claims || req.headers.origin !== origin || req.body?.csrf !== flow.csrf) throw new Error('Invalid MFA state');
    await checkMember(req, flow.claims);
    const identity = await resolveIdentity(flow.claims);
    if (!identity.verifyMfa || !await identity.verifyMfa(String(req.body.code || ''))) throw new Error('MFA failed');
    await finish(req, res, flow.claims);
  }));

  // Bind SSO-issued native sessions to the current DevAntiq browser identity.
  // This middleware adds denial checks; native auth must still follow it.
  app.use('/api', async (req, res, next) => {
    const token = String(req.headers.authorization || '').replace(/^Bearer /, '') || req.query?.token;
    if (!token) return next();
    const binding = sessionBinding(token);
    if (!binding) return next();
    try {
      if (binding.invalid) throw new Error('Invalid binding');
      await checkMember(req, binding);
      next();
    } catch { res.status(401).json({ error: 'Session DevAntiq expirée ou compte changé.' }); }
  });
}
