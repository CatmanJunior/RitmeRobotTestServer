import { readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { inspectExport } from '../../ritmerobot-frontend/scripts/package-web.mjs';

export function classifyExport(exitCode, stdout, stderr) {
    const logs = `${stdout}\n${stderr}`.replace(new RegExp(`${String.fromCharCode(27)}\\[[0-9;]*m`, 'g'), '');
    if (/SCRIPT ERROR:|ERROR:/.test(logs)) throw new Error('Godot meldde een exportfout.');
    if (exitCode === 0) return 'success';
    if ((exitCode >>> 0) === 0xc0000005 && /CrashHandlerException: Program crashed with signal 11/.test(logs)
        && /\[\s*DONE\s*\]\s*savepack/.test(logs)) return 'crash';
    throw new Error(`Godot is gestopt met exitcode ${exitCode}.`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
    try {
        const [exitCode, stdoutPath, stderrPath, exportDir] = process.argv.slice(2);
        const result = classifyExport(Number(exitCode), await readFile(stdoutPath, 'utf8'), await readFile(stderrPath, 'utf8'));
        await inspectExport(exportDir, 'ritme_robot.html');
        if (result === 'crash') console.log('Waarschuwing: Godot crashte na het exporteren; de exportbestanden zijn gecontroleerd.');
    } catch (error) {
        console.log(error.message);
        process.exitCode = 1;
    }
}
