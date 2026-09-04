// Actual isolated browser viewport capture. No mocked responses or reconstructed UI.
import fs from 'node:fs/promises';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
const require=createRequire(import.meta.url);
const {chromium}=require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const output=path.resolve(root,process.env.DEMO_RECORDING_OUTPUT || 'data/private/public-recording');
if (!output.startsWith(path.join(root,'data/private/'))) throw new Error('Use ignored recording storage');
await fs.mkdir(path.dirname(output),{recursive:true});
await fs.mkdir(output); // An existing recording is never overwritten.
await fs.mkdir(path.join(output,'frames')); await fs.mkdir(path.join(output,'screenshots'));
const credentials=await fs.readFile(path.resolve(root,
  process.env.DEMO_CREDENTIALS_FILE || 'data/public-demo-runtime/demo-credentials.txt'),'utf8');
const accounts=Object.fromEntries(credentials.trim().split('\n').map(line=>line.split(': ')));
const browser=await chromium.launch({channel:'chrome',headless:true});
const context=await browser.newContext({viewport:{width:1920,height:1080},deviceScaleFactor:1});
const page=await context.newPage();
const frames=[],scenes=[],checks=[];
let stopped=false,capturing=false,started=Date.now(),excluded=0,suspendedAt=0;
const clock=()=>((suspendedAt || Date.now())-started-excluded)/1000;
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const captureTask=(async()=>{
  while(!stopped){
    if(capturing){
      const file=`frames/${String(frames.length).padStart(5,'0')}.jpg`;
      const time=clock();
      await page.screenshot({path:path.join(output,file),type:'jpeg',quality:84});
      frames.push({file,time});
    }
    await sleep(240);
  }
})();
async function pause(){capturing=false; await sleep(350); suspendedAt=Date.now();}
function resume(){excluded+=Date.now()-suspendedAt;suspendedAt=0;capturing=true;}
async function scene(name,seconds){
  await sleep(600); // Let real UI transitions settle before the still and reading pause.
  const text=await page.locator('body').innerText();
  assert(!Object.values(accounts).some(value=>text.includes(value)),'Credentials must never be visible');
  await page.screenshot({path:path.join(output,'screenshots',name+'.png')});
  scenes.push({name,time:clock()});
  console.log('Scene verified:',name);
  await sleep(seconds*1000);
}
async function login(role){
  await pause();
  if(await page.getByRole('button',{name:'Sign out'}).count())
    await page.getByRole('button',{name:'Sign out'}).click();
  await page.getByLabel('Username',{exact:true}).fill(role);
  await page.getByLabel('Password',{exact:true}).fill(accounts[role]);
  await page.getByRole('button',{name:'Sign in',exact:true}).click();
  await page.getByRole('heading',{name:'Ask company knowledge'}).waitFor();
  resume();
}
async function ask(question,expected){
  const previousCount=await page.locator('.message-assistant').count();
  await page.getByLabel('Ask a grounded question').fill(question);
  const response=page.waitForResponse(r=>r.url().endsWith('/api/query') && r.request().method()==='POST');
  await page.locator('.composer button[type=submit]').click();
  const result=await (await response).json();
  assert(result.answer.includes(expected),`Expected grounded answer: ${expected}`);
  const message=page.locator('.message-assistant').nth(previousCount);
  await message.waitFor();
  await message.getByText(expected,{exact:false}).first().waitFor();
  await message.evaluate(node=>node.scrollIntoView({block:'center',behavior:'instant'}));
  checks.push({question,answer:result.answer,source_files:result.sources.map(s=>s.source_file)});
  return result;
}
try{
  await page.goto(process.env.DEMO_FRONTEND_URL || 'http://127.0.0.1:5173');
  await page.getByRole('button',{name:'Sign in',exact:true}).waitFor();
  started=Date.now();capturing=true;
  await scene('01-login',5);
  await login('employee');await scene('02-employee-workspace',5);
  await ask('NSTR-VESSEL-731 material, capacity and MOQ?','144 units');
  await scene('03-grounded-product',16);
  await page.locator('.message-assistant').last().locator('.citation-chip').first().click();
  await page.getByRole('dialog').waitFor();
  await page.locator('.excerpt-block').waitFor();
  assert((await page.locator('.excerpt-block').innerText()).includes('18/8 stainless steel'));
  await scene('04-evidence',13);
  await page.getByRole('button',{name:'Close evidence'}).click();
  const missing=await ask('What is the current lead time for NSTR-LANTERN-864?','not verified');
  assert(!missing.sufficient_information);
  await scene('05-unverified-field',14);
  await ask('Historical NSTR-VESSEL-731 payment terms and Incoterms?','not current policy');
  await scene('06-historical-evidence',16);
  await login('admin');await page.getByRole('button',{name:'Knowledge sources',exact:true}).click();
  await page.getByLabel('Choose a knowledge source').setInputFiles(
    path.join(root,'data/demo/updates/northstar-proposed-update.csv'));
  await page.getByRole('button',{name:'Create review items',exact:true}).waitFor();
  await page.getByRole('button',{name:'Create review items',exact:true}).click();
  await page.getByText('1 review item(s) created. No current facts changed.',{exact:true}).waitFor();
  await scene('07-controlled-ingestion',9);
  await login('reviewer');await page.getByRole('button',{name:'Review queue',exact:true}).click();
  await page.locator('.value-compare').waitFor();
  assert((await page.locator('.value-compare').innerText()).includes('144 units'));
  assert((await page.locator('.value-compare').innerText()).includes('180 units'));
  await scene('08-pending-conflict',13);
  await page.getByLabel('Reviewer note',{exact:true}).fill('Synthetic replenishment revision verified against the proposed source.');
  await page.getByRole('button',{name:'Approve fact',exact:true}).click();
  await page.getByText('Approved with an auditable reviewer note.',{exact:true}).waitFor();
  await scene('09-review-approved',8);
  await page.getByRole('button',{name:'Product master',exact:true}).click();
  await page.getByPlaceholder('SKU or Product ID').fill('NSTR-VESSEL-731');
  const fact=page.locator('.fact-cell').filter({hasText:'moq'});
  await fact.waitFor();await fact.scrollIntoViewIfNeeded();
  assert((await fact.innerText()).includes('180 units'));
  await fact.click();await page.locator('.history-panel').waitFor();
  await page.locator('.history-panel').scrollIntoViewIfNeeded();
  await scene('10-master-provenance',13);
  await login('admin');await page.getByRole('button',{name:'Knowledge sources',exact:true}).click();
  await page.getByRole('button',{name:'Re-index configured source',exact:true}).click();
  await page.locator('.job-card .state-completed').first().waitFor({timeout:30000});
  await scene('11-index-updated',5);
  await login('employee');
  const updated=await ask('NSTR-VESSEL-731 MOQ?','180 units');
  assert(!updated.answer.includes('144 units'));
  assert(updated.sources.some(s=>s.approval_change_id),'Must cite approved change');
  await scene('12-governed-answer',14);
  await page.locator('.message-assistant').last().locator('.citation-chip').first().click();
  await page.locator('.excerpt-block').waitFor();
  assert((await page.locator('.excerpt-block').innerText()).includes('180 units'));
  await scene('13-governed-evidence',8);
  await page.getByRole('button',{name:'Close evidence'}).click();
  await scene('14-finish',3);
}finally{
  capturing=false;stopped=true;await captureTask;
  const duration=clock();
  await fs.writeFile(path.join(output,'frames.json'),JSON.stringify({width:1920,height:1080,duration,frames}));
  await fs.writeFile(path.join(output,'workflow.json'),JSON.stringify({duration,scenes,checks},null,2));
  await browser.close();
}
console.log('Actual UI workflow completed; credential entry omitted from captured time.');
