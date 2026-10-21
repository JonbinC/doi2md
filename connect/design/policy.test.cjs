const test = require('node:test');
const assert = require('node:assert/strict');
const p = require('./policy.js');
const base = {signedIn:true,keyStatus:'verified',relayOnline:true,browserReady:true,hostVerified:true,cloudCommitted:true,accessScopeId:'demo-device'};
test('five GiB is exact and explicit',()=>assert.equal(p.QUOTA_BYTES,5368709120));
test('anonymous users cannot inherit account capabilities',()=>{
 const r=p.readiness({...base,signedIn:false});
 assert.deepEqual(r.steps,['pending','pending','pending']); assert.equal(r.canTryOpenPapers,false); assert.equal(r.cloudReady,false);
});
test('open access trial does not depend on a key or relay',()=>assert.equal(p.readiness({signedIn:true}).canTryOpenPapers,true));
test('skipped keys are not verified keys',()=>{
 const r=p.readiness({signedIn:true,keyStatus:'skipped'}); assert.equal(r.steps[1],'skipped'); assert.equal(r.keyVerified,false);
});
test('online is not browser ready or entitlement',()=>{
 const r=p.readiness({...base,browserReady:false}); assert.equal(r.browserReady,false);assert.equal(r.probeOutcome,'unknown');assert.equal(r.verifiedArticleId,null);
});
test('all steps do not imply publisher access',()=>{
 const r=p.readiness(base);assert.deepEqual(r.steps,['complete','complete','complete']);assert.equal(r.allPublishersVerified,false);
});
for(const outcome of ['entitled','metadata_only','not_entitled','key_invalid','probe_failed']) test(outcome+' is not verified body',()=>{
 const r=p.readiness({...base,probe:{outcome,bodyVerified:true,documentId:'D1',scopeId:'demo-device',ageSeconds:0}});assert.equal(r.verifiedArticleId,null);
});
test('fresh matching successful article probe is scoped',()=>assert.equal(p.readiness({...base,probe:{outcome:'full_text_ok',bodyVerified:true,documentId:'D1',scopeId:'demo-device',ageSeconds:5}}).verifiedArticleId,'D1'));
for(const patch of [{bodyVerified:false},{ageSeconds:301},{ageSeconds:-1},{scopeId:'other-device'},{documentId:''}]) test('reject invalid probe '+JSON.stringify(patch),()=>{
 assert.equal(p.readiness({...base,probe:{outcome:'full_text_ok',bodyVerified:true,documentId:'D1',scopeId:'demo-device',ageSeconds:5,...patch}}).verifiedArticleId,null);
});
test('offline helper does not invalidate saved cloud reading',()=>{
 const r=p.readiness({...base,relayOnline:false});assert.equal(r.canUseSavedLibrary,true);assert.equal(r.steps[2],'partial');
});
test('upload begins only when reservation fits',()=>{
 assert.equal(p.canReserve({usedBytes:90,reservedBytes:5,incomingBytes:5,quotaBytes:100}),true);
 assert.equal(p.canReserve({usedBytes:90,reservedBytes:6,incomingBytes:5,quotaBytes:100}),false);
});
for(const value of [-1,0.5,Infinity,Number.MAX_SAFE_INTEGER+1]) test('invalid byte count '+value,()=>assert.throws(()=>p.canReserve({usedBytes:value,reservedBytes:0,incomingBytes:1})));
test('local and web clocks are separate',()=>{
 const scope={accountId:'a',libraryType:'user',libraryId:'1'};
 assert.notEqual(p.syncPartition({...scope,transport:'web'}),p.syncPartition({...scope,transport:'local',serverId:'one'}));
 assert.notEqual(p.syncPartition({...scope,transport:'local',serverId:'one'}),p.syncPartition({...scope,transport:'local',serverId:'two'}));
 assert.throws(()=>p.syncPartition({...scope,transport:'local'}));
});
test('checkpoint requires complete and stable snapshot',()=>{
 const batch={priorVersion:5,responseVersions:[7,7,7],allPagesSaved:true,deletionsProcessed:true};
 assert.equal(p.checkpoint(batch),7);
 for(const patch of [{responseVersions:[7,8]},{allPagesSaved:false},{deletionsProcessed:false},{pendingErrors:['ABC']}]) assert.equal(p.checkpoint({...batch,...patch}),5);
});
test('invalid missing or older versions cannot advance',()=>{
 for(const responseVersions of [[],[4],[NaN]]) assert.equal(p.checkpoint({priorVersion:5,responseVersions,allPagesSaved:true,deletionsProcessed:true}),5);
});
