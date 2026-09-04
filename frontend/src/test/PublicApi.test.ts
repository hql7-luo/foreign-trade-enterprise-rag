import { afterEach, expect, test, vi } from 'vitest';
import { api } from '../api';
afterEach(()=>{vi.unstubAllGlobals();vi.unstubAllEnvs();});
test.each([429,503])('sanitizes error %s without exposing backend details',async(status)=>{
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({detail:'internal-detail'}),{status})));
  await expect(api.query('fixture-only','example',false)).rejects.not.toThrow('internal-detail');
});
test('expired session emits an application event',async()=>{
  const listener=vi.fn();window.addEventListener('rag:session-expired',listener);
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('{}',{status:401})));
  await expect(api.products('fixture-only')).rejects.toThrow(); expect(listener).toHaveBeenCalled();
  window.removeEventListener('rag:session-expired',listener);
});
test('same-origin constraint blocks accidental token transmission',async()=>{
  vi.stubEnv('VITE_API_BASE_URL','https://example.invalid/api');
  const fetcher=vi.fn();vi.stubGlobal('fetch',fetcher);
  await expect(api.products('fixture-only')).rejects.toThrow();expect(fetcher).not.toHaveBeenCalled();
});
