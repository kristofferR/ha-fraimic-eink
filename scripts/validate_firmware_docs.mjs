import {access, readFile, readdir} from 'node:fs/promises';
import {dirname, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';

// Optional repo argument also supports running a private copy of this checker.
const repo = resolve(process.argv[2] ?? fileURLToPath(new URL('..', import.meta.url)));
const root = resolve(repo, 'docs/firmware');
const errors = [];
let links = 0;
const privateKeyFile = process.env.FRAIMIC_RESEARCH_DEVICE_KEY_FILE;
const privateKey = privateKeyFile ? (await readFile(privateKeyFile, 'utf8')).trim() : null;
if (privateKeyFile && !privateKey) errors.push('Private credential scan file is empty');
const slug = text => text.toLowerCase().replace(/[`*]/g, '').replace(/[^\p{L}\p{N}_ -]/gu, '').replace(/ /g, '-');
for (const name of await readdir(root)) {
  if (!/\.(md|json)$/.test(name)) continue;
  const path = resolve(root, name);
  const source = await readFile(path, 'utf8');
  if (name.endsWith('.json')) {
    try { JSON.parse(source); } catch { errors.push(`${name}: invalid JSON`); }
  }
  if (privateKey && source.includes(privateKey)) errors.push(`${name}: provisioned credential`);
  if (/eyJ[A-Za-z0-9_-]{25,}\.[A-Za-z0-9_-]+\.|-----BEGIN [A-Z ]*PRIVATE KEY|[?&](?:X-Amz-Signature|Signature|AWSAccessKeyId)=|[\w.+-]+@risanger\.no/i.test(source)) {
    errors.push(`${name}: private material pattern`);
  }
  if (!name.endsWith('.md')) continue;
  for (const match of source.matchAll(/\[[^\]]*\]\(([^)]+)\)/g)) {
    const target = match[1];
    if (/^(https?:|mailto:)/.test(target)) continue;
    const [file, anchor] = target.split('#');
    const destination = resolve(dirname(path), file || name);
    try { await access(destination); links++; } catch { errors.push(`${name}: missing ${file}`); continue; }
    if (anchor && destination.endsWith('.md')) {
      const other = await readFile(destination, 'utf8');
      const headings = [...other.matchAll(/^#{1,6}\s+(.+)$/gm)].map(x => slug(x[1]));
      if (!headings.includes(anchor)) errors.push(`${name}: missing anchor ${target}`);
    }
  }
}

const todo = await readFile(resolve(root, 'research-todo.md'), 'utf8');
const checks = [...todo.matchAll(/^- \[([ x])\] \*\*([A-Z]\d\d) ·/gm)];
const originalIds = Object.entries({C:12, A:7, R:12, S:7, D:8, N:8, H:7, B:3, E:3})
  .flatMap(([prefix, count]) => Array.from({length:count}, (_, i) => `${prefix}${String(i+1).padStart(2, '0')}`));
const ids = checks.map(x => x[2]);
if (new Set(ids).size !== ids.length || originalIds.some(id => !ids.includes(id))) {
  errors.push('Original checklist IDs must be retained once each');
}
const statuses = Object.fromEntries(['Complete', 'Research', 'Waiting for device', 'Needs implementation', 'Waiting for recovery', 'Deferred', 'Ongoing'].map(s => [s, 0]));
let milestones = 0;
let completedMilestones = 0;
for (const [i, check] of checks.entries()) {
  const id = check[2];
  const block = todo.slice(check.index, checks[i+1]?.index ?? todo.length).split('\n## ')[0];
  const status = block.match(/^  Status: \*\*([^*]+)\*\*\.$/m)?.[1];
  if (!Object.hasOwn(statuses, status)) errors.push(`${id}: missing or invalid status`);
  else statuses[status]++;
  const children = [...block.matchAll(/^  - \[([ x])\] (.+)$/gm)];
  if (!children.length) errors.push(`${id}: missing milestones`);
  milestones += children.length;
  completedMilestones += children.filter(x => x[1] === 'x').length;
  const done = check[1] === 'x';
  if (done !== (status === 'Complete')) errors.push(`${id}: checkbox/status mismatch`);
  if (done !== children.every(x => x[1] === 'x')) errors.push(`${id}: completion contradicts remaining milestones`);
  for (const child of children) {
    if (child[1] === 'x' && !/\[[^\]]+\]\([^)]+\)/.test(child[2])) errors.push(`${id}: completed milestone lacks evidence link`);
    if (child[1] === ' ' && !/^\*\*(Next|Implementation|Blocked|Deferred):\*\*/.test(child[2])) errors.push(`${id}: remaining milestone lacks work category`);
  }
}
const completed = checks.filter(x => x[1] === 'x').map(x => x[2]);
const summary = todo.match(/\*\*(\d+) of (\d+) original items complete; (\d+) of (\d+) concrete milestones complete\.\*\*/);
if (!summary || summary.slice(1).map(Number).join(',') !== [completed.length, checks.length, completedMilestones, milestones].join(',')) {
  errors.push('Checklist summary counts do not match checkboxes');
}
const completedSummary = todo.match(/Completed original items: \*\*([^*]+)\*\*/)?.[1].split(', ');
if (completedSummary?.join(',') !== completed.join(',')) errors.push('Completed item summary is stale');
for (const [status, count] of Object.entries(statuses)) {
  const row = todo.split('\n').find(line => line.startsWith(`| ${status} |`));
  if (!row || Number(row.split('|')[2].trim()) !== count) errors.push(`${status}: summary table count is stale`);
}

const map = JSON.parse(await readFile(resolve(root, 'address-map.json'), 'utf8'));
if (new Set(map.entries.map(x => x.address)).size !== map.entries.length) errors.push('Duplicate addresses');
const identity = JSON.parse(await readFile(resolve(root, 'firmware-identity.json'), 'utf8'));
if (identity.sha256 !== map.firmware_sha256 || identity.descriptor_build_timezone !== null || identity.verified_custom_boot !== false) {
  errors.push('Firmware identity or established unknown-state boundary mismatch');
}
console.log(JSON.stringify({links, addresses:map.entries.length, checklist:checks.length, completed, completedMilestones, milestones, statuses, privateCredentialScan:privateKey !== null, errors}));
if (errors.length) process.exitCode = 1;
