const fs = require('fs');
const html = fs.readFileSync(process.argv[2], 'utf8');
const script = html.match(/<script>([\s\S]*)<\/script>/i);
if (!script) throw new Error('inline app script missing');
new Function(script[1]);
for (const marker of ['const LABS=', 'const SCENARIOS=', 'function runCommand', 'function deployIncident']) {
  if (!html.includes(marker)) throw new Error(`missing ${marker}`);
}
console.log('JavaScript parsed and app markers are present.');
