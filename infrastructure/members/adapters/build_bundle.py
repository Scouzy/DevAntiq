"""Prepare reviewed patches against exact VPS source hashes; never touch production."""
import hashlib
import json
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ENTRIES = {'g1crm':'server/index.js', 'g1profil':'server/src/index.js',
           'sentinet':'server/index.js', 'livemonitor':'backend/server.js'}
IMPORTS = {
 'g1crm': "import { installDevAntiq } from './devantiq-sso/connector.mjs';\n",
 'g1profil': "import { installDevAntiq } from './devantiq-sso/connector.mjs';\nimport { randomBytes as devantiqRandomBytes } from 'node:crypto';\n",
 'livemonitor': "import { installDevAntiq } from './devantiq-sso/connector.mjs';\nimport devantiqDb from './db.js';\nimport devantiqBcrypt from 'bcryptjs';\nimport devantiqJwt from 'jsonwebtoken';\nimport { SECRET as devantiqSecret } from './auth.js';\nimport { randomBytes as devantiqRandomBytes } from 'node:crypto';\n",
 'sentinet': "const { installDevAntiq, guardWebSocket } = require('./devantiq-sso/connector.mjs')\n",
}
ANCHORS = {'g1crm': '// --- Sonde de disponibilité', 'g1profil':'// ─── État du service',
           'livemonitor':'/* ── Security middleware', 'sentinet':"app.post('/api/auth/login'"}


def once(source, old, new):
    if source.count(old) != 1:
        raise ValueError('Expected source marker is absent or duplicated')
    return source.replace(old, new, 1)


def build(source, output):
    output.mkdir(parents=True, exist_ok=False)
    manifest = {}
    def save(app, relative, original, updated):
        dest = output / app / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(updated, encoding='utf-8', newline='\n')
        manifest[app + '/' + relative] = {
            'before':hashlib.sha256(original).hexdigest(),
            'after':hashlib.sha256(dest.read_bytes()).hexdigest()}
    for app, relative in ENTRIES.items():
        original = (source / app / relative).read_bytes()
        code = original.decode().replace('\r\n','\n')
        if 'installDevAntiq' in code:
            raise ValueError('Already adapted source requires review')
        snippet = (HERE / (app + '.js.txt')).read_text(encoding='utf-8')
        code = once(code, ANCHORS[app], snippet + '\n' + ANCHORS[app])
        code = once(code, "'use strict'", "'use strict'\n" + IMPORTS[app]) if app == 'sentinet' else IMPORTS[app] + code
        if app == 'sentinet':
            code = once(code, "wss.on('connection', (ws, req) => {", "wss.on('connection', async (ws, req) => {")
            code = once(code, '  let dead = false', "  if (!await guardWebSocket('sentinet', ws, req, new URL(req.url,'http://localhost').searchParams.get('token'))) return\n  let dead = false")
            code = once(code, "if (c.readyState === WebSocket.OPEN) c.send(s)", "if (c.readyState === WebSocket.OPEN && c._devantiqVerified) c.send(s)")
        save(app,relative,original,code)
        folder = output / app / Path(relative).parent / 'devantiq-sso'
        folder.mkdir()
        for name in ('connector.mjs','package.json','package-lock.json'):
            shutil.copyfile(HERE / name, folder / name)
    relative = 'backend/websocket.js'
    original = (source / 'livemonitor' / relative).read_bytes()
    code = original.decode().replace('\r\n','\n')
    code = "import { guardWebSocket } from './devantiq-sso/connector.mjs';\n" + code
    code = once(code, 'wss.on("connection", (ws, req) => {', 'wss.on("connection", async (ws, req) => {')
    code = once(code, '    clients.add(ws);', "    if (!await guardWebSocket('livemonitor', ws, req)) return;\n    clients.add(ws);")
    save('livemonitor', relative, original, code)
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print('Prepared four adapters with exact source hashes:', output)


if __name__ == '__main__':
    build(Path(sys.argv[1]), Path(sys.argv[2]))
