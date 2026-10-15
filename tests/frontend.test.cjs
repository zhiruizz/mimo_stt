const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '../frontend/index.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const key = 'mimo_stt_settings';

function page(saved, {blocked = false, writeBlocked = false, raw} = {}) {
    const elements = new Map();
    for (const [, id] of html.matchAll(/id="([^"]+)"/g)) {
        elements.set(id, {
            value: '', style: {}, checked: false, disabled: false, textContent: '',
            classList: {add() {}, remove() {}}, listeners: {},
            addEventListener(name, fn) { this.listeners[name] = fn; },
        });
    }
    const options = [...html.match(/<select id="modelSelect">([\s\S]*?)<\/select>/)[1]
        .matchAll(/value="([^"]+)"/g)].map(x => ({value: x[1]}));
    elements.get('modelSelect').options = options;
    elements.get('modelSelect').value = options[0].value;
    let stored = raw === undefined ? (saved === undefined ? null : JSON.stringify(saved)) : raw;
    const requests = [];
    const context = vm.createContext({
        document: {getElementById: id => elements.get(id)},
        localStorage: {
            getItem(name) { assert.equal(name, key); if (blocked) throw Error('blocked'); return stored; },
            setItem(name, value) { assert.equal(name, key); if (blocked || writeBlocked) throw Error('blocked'); stored = value; },
        },
        FormData: class {
            constructor() { this.data = new Map(); }
            append(k, v) { this.data.set(k, v); }
            get(k) { return this.data.get(k); }
        },
        fetch: async (url, options) => {
            requests.push({url, ...options});
            return {json: async () => ({task_id: 'fixture-task'})};
        },
        setInterval() { return 1; }, clearInterval() {},
    });
    vm.runInContext(script, context);
    return {elements, context, requests, settings: () => JSON.parse(stored || '{}'),
        model: () => vm.runInContext('getModel()', context)};
}

test('fresh, malformed, null and inaccessible settings use Flash', () => {
    for (const p of [page(), page(undefined, {raw: '{bad'}), page(undefined, {raw: 'null'}),
                     page(undefined, {raw: '[]'}), page(undefined, {blocked: true})]) {
        assert.equal(p.model(), 'mimo-v2.6-flash');
        assert.equal(p.elements.get('modelSelect').value, 'mimo-v2.6-flash');
    }
    assert.ok(!html.includes('<option value="mimo-v2-omni">'));
});

for (const [old, current] of [['mimo-v2.5', 'mimo-v2.6-flash'], ['mimo-v2-omni', 'mimo-v2.6-flash'],
                             ['mimo-v2.5-pro', 'mimo-v2.6-pro'], ['mimo-v2-flash', 'mimo-v2.6-flash'],
                             ['mimo-v2-pro', 'mimo-v2.6-pro']]) {
    test(`migrates saved ${old}, retaining every other setting`, () => {
        const saved = {model: ' ' + old + ' ', apiEndpoint: 'https://fixture.invalid/v1/chat/completions',
            apiKey: 'test-only', prompt: '保留逐字转录', outputDir: 'fixture-output', autoSave: true, extra: 42};
        const p = page(saved);
        assert.equal(p.model(), current);
        assert.deepEqual(p.settings(), {...saved, model: current});
        assert.equal(p.elements.get('apiKeyInput').value, saved.apiKey);
        assert.equal(p.elements.get('apiEndpointInput').value, saved.apiEndpoint);
        assert.equal(p.elements.get('promptInput').value, saved.prompt);
        assert.equal(p.elements.get('outputDirInput').value, saved.outputDir);
        assert.equal(p.elements.get('autoSaveCheck').checked, true);
        assert.equal(page(p.settings()).model(), current); // Reload is idempotent.
    });
}

test('ASR and unknown custom IDs survive; ASR disables prompt only in UI', () => {
    for (const model of ['mimo-v2.5-asr', 'mimo-v2.5-tts', 'my-custom-model']) {
        const p = page({model, prompt: 'saved prompt'});
        assert.equal(p.model(), model);
        assert.equal(p.elements.get('promptInput').disabled, model === 'mimo-v2.5-asr');
        assert.equal(p.elements.get('promptInput').value, 'saved prompt');
    }
});

test('custom input aliases and blank fallback normalize at save and submit', () => {
    const p = page({model: 'my-custom-model'});
    for (const [input, expected] of [['mimo-v2.5', 'mimo-v2.6-flash'], ['', 'mimo-v2.6-flash'],
                                   ['mimo-v2.5-asr', 'mimo-v2.5-asr']]) {
        p.elements.get('modelCustomInput').value = input;
        p.elements.get('modelCustomInput').listeners.change();
        assert.equal(p.model(), expected);
        assert.equal(p.settings().model, expected);
    }
});

test('write-blocked storage still migrates effective model and allows saving UI settings', () => {
    const p = page({model: 'mimo-v2.5', apiKey: 'test-only'}, {writeBlocked: true});
    assert.equal(p.model(), 'mimo-v2.6-flash');
    assert.doesNotThrow(() => p.elements.get('apiKeyInput').listeners.change());
});

test('transcribe submits migrated model and original endpoint through the actual click handler', async () => {
    const p = page({model: 'mimo-v2-omni', apiKey: 'test-only', apiEndpoint: 'https://fixture.invalid/v1/chat/completions'});
    p.elements.get('fileInput').listeners.change({target: {files: [{name: 'fixture.wav', size: 1234}]}});
    await p.elements.get('startBtn').listeners.click();
    assert.equal(p.requests.length, 1);
    assert.equal(p.requests[0].url, '/api/transcribe');
    assert.equal(p.requests[0].body.get('model'), 'mimo-v2.6-flash');
    assert.equal(p.requests[0].body.get('api_endpoint'), 'https://fixture.invalid/v1/chat/completions');
});
