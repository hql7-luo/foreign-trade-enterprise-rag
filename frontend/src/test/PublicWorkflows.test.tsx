import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import axe from 'axe-core';
import { afterEach, expect, test, vi } from 'vitest';
import { api } from '../api';
import { LoginPage } from '../components/LoginPage';
import { Shell } from '../components/Shell';
import { EvidenceDrawer } from '../components/EvidenceDrawer';
import { ChatPage } from '../pages/ChatPage';
import { ProductsPage } from '../pages/ProductsPage';
import { ReviewPage } from '../pages/ReviewPage';
import { SourcesPage } from '../pages/SourcesPage';
import type { Citation, FactChange, QueryResult } from '../types';

afterEach(() => vi.restoreAllMocks());
const citation: Citation = { citation_id:1, label:'Synthetic catalog row 2',
  source_file:'northstar-products.csv', source_type:'csv', row_number:2, sheet:null,
  section:null, product_sku:'NSTR-VESSEL-731', product_id:'NSITEM-V731',
  source_modified_at:'2025-11-06T00:00:00Z', chunk_id:'public-fixture-chunk',
  source_version:'synthetic-fixture-version', approval_change_id:null,
  authority_class:'A', knowledge_status:'current_approved' };
const answer: QueryResult = { answer:'The material is 18/8 stainless steel.',
  sufficient_information:true, sources:[citation], retrieved_context:[], structured_matches:[],
  claims:[{text:'NSTR-VESSEL-731 — material: 18/8 stainless steel.', supported:true,
    sources:[citation], claim_type:'material'}], conflicts:[], answer_context_chars:180,
  answer_context_chunks:1, debug:null };
const proposal: FactChange = { id:'synthetic-change', canonical_product_id:'NSITEM-V731',
  product_sku:'NSTR-VESSEL-731', field_name:'moq', proposed_value:'180 units',
  existing_value:'144 units', source_file:'northstar-proposed-update.csv',
  source_version:'synthetic-fixture-version', source_row:2,
  evidence:{statement:'moq = 180 units'}, status:'pending', created_at:'2025-11-07T00:00:00Z',
  decided_at:null, reviewer_id:null, reason:null, events:[] };

test('employee navigation excludes reviewer and administrator actions', () => {
  render(<Shell user={{username:'employee',display_name:'Demo Employee',role:'employee'}}
    page='assistant' onPage={vi.fn()} onLogout={vi.fn()}>Workspace</Shell>);
  expect(screen.getByRole('button',{name:'Ask knowledge'})).toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'Review queue'})).not.toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'Knowledge sources'})).not.toBeInTheDocument();
});

test('chat submits a synthetic product question and opens its claim evidence', async () => {
  const query = vi.spyOn(api,'query').mockResolvedValue(answer);
  const inspect = vi.fn(); const user = userEvent.setup();
  render(<ChatPage token='fixture-only' role='employee' onEvidence={inspect}/>);
  await user.click(screen.getByRole('button',{name:'Show NSTR-VESSEL-731 specifications.'}));
  expect(await screen.findByText(answer.claims[0].text)).toBeInTheDocument();
  expect(query).toHaveBeenCalledWith('fixture-only','Show NSTR-VESSEL-731 specifications.',false);
  await user.click(screen.getByRole('button',{name:/northstar-products.csv/}));
  expect(inspect).toHaveBeenCalledWith(citation);
});

test('unsupported fact is visibly unverified', async () => {
  vi.spyOn(api,'query').mockResolvedValue({...answer, sufficient_information:false, sources:[],
    claims:[{text:'Lead time is not verified.',supported:false,sources:[],claim_type:'lead_time'}]});
  render(<ChatPage token='fixture-only' role='employee' onEvidence={vi.fn()}/>);
  await userEvent.click(screen.getByRole('button',{name:'What is the current lead time for NSTR-LANTERN-864?'}));
  expect(await screen.findByText('Lead time is not verified.')).toBeInTheDocument();
});

test('evidence drawer is labeled, focusable and closes with Escape', async () => {
  vi.spyOn(api,'evidence').mockResolvedValue({ ...citation, row_start:2, row_end:2,
    excerpt:'material: 18/8 stainless steel', source_date:'2025-11-06' });
  const close=vi.fn(); render(<EvidenceDrawer citation={citation} token='fixture-only' onClose={close}/>);
  expect(await screen.findByText('material: 18/8 stainless steel')).toBeInTheDocument();
  expect(screen.getByRole('dialog',{name:'northstar-products.csv'})).toHaveAttribute('aria-modal','true');
  expect(screen.getByRole('button',{name:'Close evidence'})).toHaveFocus();
  await userEvent.keyboard('{Escape}'); expect(close).toHaveBeenCalled();
});

test('review approval requires a note and sends the exact decision', async () => {
  vi.spyOn(api,'changes').mockResolvedValue([proposal]);
  vi.spyOn(api,'change').mockResolvedValue(proposal);
  const decide=vi.spyOn(api,'decide').mockResolvedValue({...proposal,status:'approved'});
  render(<ReviewPage token='fixture-only'/>);
  const button=await screen.findByRole('button',{name:'Approve fact'});
  expect(button).toBeDisabled();
  await userEvent.type(screen.getByLabelText('Reviewer note'),'Synthetic source revision checked');
  await userEvent.click(button);
  await waitFor(()=>expect(decide).toHaveBeenCalledWith('fixture-only','synthetic-change','approve','Synthetic source revision checked'));
});

test('login has no automated accessibility violations', async () => {
  const {container}=render(<LoginPage onLogin={vi.fn()}/>);
  const result=await axe.run(container,{rules:{'color-contrast':{enabled:false}}});
  expect(result.violations).toEqual([]);
  expect(screen.getByLabelText('Password')).toHaveAttribute('type','password');
});

test('empty product master has an accessible empty state', async () => {
  vi.spyOn(api,'products').mockResolvedValue([]);
  const {container}=render(<ProductsPage token='fixture-only'/>);
  await waitFor(()=>expect(api.products).toHaveBeenCalled());
  expect((await axe.run(container,{rules:{'color-contrast':{enabled:false}}})).violations).toEqual([]);
});

test('empty review queue is accessible', async () => {
  vi.spyOn(api,'changes').mockResolvedValue([]);
  const {container}=render(<ReviewPage token='fixture-only'/>);
  await waitFor(()=>expect(api.changes).toHaveBeenCalled());
  expect((await axe.run(container,{rules:{'color-contrast':{enabled:false}}})).violations).toEqual([]);
});

test('admin sources page is accessible when no sources exist', async () => {
  vi.spyOn(api,'sources').mockResolvedValue([]); vi.spyOn(api,'stagedSources').mockResolvedValue([]);
  vi.spyOn(api,'ingestionJobs').mockResolvedValue([]);
  const {container}=render(<SourcesPage token='fixture-only'/>);
  await waitFor(()=>expect(api.sources).toHaveBeenCalled());
  expect((await axe.run(container,{rules:{'color-contrast':{enabled:false}}})).violations).toEqual([]);
});
