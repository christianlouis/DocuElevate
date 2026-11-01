const fs = require('fs');
const vm = require('vm');
const ts = require(process.cwd() + '/mobile/node_modules/typescript');
const assert = require('assert');
(async () => {
  const calls = [];
  const caps = { local_signup: true, smtp_configured: true, terms_version: 't2', privacy_version: 'p3', terms_url: '/terms', privacy_url: '/privacy', csrf_token: 'csrf-123' };
  const fetch = async (url, options = {}) => {
    calls.push({ url, options });
    return { ok: true, status: 200, json: async () => url.endsWith('/capabilities') ? caps : { email_verification_required: true } };
  };
  const source = fs.readFileSync('mobile/src/services/api.ts', 'utf8');
  const js = ts.transpile(source, { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 });
  const module = { exports: {} };
  vm.runInNewContext(js, { module, exports: module.exports, require: () => ({ getItemAsync: async () => 'old-server-token', setItemAsync: async () => {} }), fetch, URL, FormData, console });
  const api = module.exports.default;
  await api.authCapabilities('https://new.example');
  await api.init('https://new.example');
  const legal = { accept_terms: true, accept_privacy: true, terms_version: caps.terms_version, privacy_version: caps.privacy_version };
  await api.signup({ email: 'a@b.test', username: 'tester', password: 'password1', password_confirm: 'password1', ...legal });
  await api.resendVerification('a@b.test');
  await api.completeOnboarding(legal);
  for (const call of calls.slice(1, 3)) {
    assert.equal(call.options.credentials, 'include');
    assert.equal(call.options.headers['X-CSRF-Token'], 'csrf-123');
    assert.equal(call.options.headers.Authorization, undefined);
  }
  assert.deepStrictEqual(JSON.parse(calls[1].options.body).terms_version, 't2');
  assert.deepStrictEqual(JSON.parse(calls[3].options.body), legal);
  const web = fs.readFileSync('frontend/templates/signup.html', 'utf8');
  let script = web.match(/Alpine\.data\('signupForm', \(\) => \(\{([\s\S]*?)\n                \}\)\);/)[1];
  script = '({' + script.replace(/\{\{[\s\S]*?\}\}/g, '"message"') + '\n})';
  const webCalls = [];
  const form = vm.runInNewContext(script, { fetch: async (url, opts) => { webCalls.push({ url, opts }); return {ok: true, json: async () => url.endsWith('capabilities') ? caps : {email_verification_required: true}}; }, window: {location: {}}, console });
  await form.init();
  Object.assign(form, { email:'a@b.test', username:'tester', password:'password1', password_confirm:'password1', terms_accepted:true, privacy_accepted:true });
  await form.submit();
  const payload = JSON.parse(webCalls[1].opts.body);
  for (const [key, value] of Object.entries(legal)) assert.equal(payload[key], value);
  assert.equal(payload.terms_accepted, undefined);
  const onboardingTemplate = fs.readFileSync('frontend/templates/onboarding.html', 'utf8');
  const onboardingSource = onboardingTemplate.match(/function onboardingWizard\(\) \{[\s\S]*?\n\}\n<\/script>/)[0]
    .replace(/<\/script>$/, '').replace(/\{\{[\s\S]*?\}\}/g, 'null');
  const onboardingCalls = [];
  const wizard = vm.runInNewContext(onboardingSource + '\nonboardingWizard()', {
    fetch: async (url, opts) => { onboardingCalls.push({url, opts}); return {ok: true, json: async () => ({redirect_url: '/upload'})}; },
    window: {location: {}}, onboardingI18n: {stepLabels: []}, console,
  });
  await wizard.completeOnboarding();
  assert.equal(onboardingCalls.length, 0);
  wizard.capabilities = caps;
  wizard.legalAccepted = true;
  await wizard.completeOnboarding();
  const completion = JSON.parse(onboardingCalls[0].opts.body);
  for (const [key, value] of Object.entries(legal)) assert.equal(completion[key], value);
  console.log('Mobile public CSRF and consent requests, web signup, and onboarding consent contracts passed');
})().catch(e => { console.error(e); process.exit(1); });
