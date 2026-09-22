import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import LocalHarnessConfigurations from '@/components/LocalHarnessConfigurations.vue'
import { preferences } from '@/composables/preferences'
const api=vi.hoisted(()=>({options:vi.fn(),harnesses:vi.fn(),saveHarness:vi.fn()}))
vi.mock('@/api/localConfiguration',()=>({localConfigurationApi:api}))
const preset={profile_id:'direct-template',harness_id:'direct-model',version:'v1',reasoning_effort:null,tool_surface:[],supported_provider_profile_ids:['local-model-v1']}
const stored={configuration_id:'my-runtime',revision:1,name:'My runtime',enabled:true,template_profile_id:preset.profile_id,harness_id:'direct-model',template_digest:'digest',profile:{profile_id:'local-harness-my-runtime-v1',supported_provider_profile_ids:['local-model-v1'],harness_config_identity:'frozen'}}
const editor=()=>mount(LocalHarnessConfigurations,{props:{token:'test-token',profiles:[]}})
beforeEach(()=>{vi.resetAllMocks();preferences.language='zh-CN';api.options.mockResolvedValue({model_controls:[],harness_templates:[preset]});api.harnesses.mockResolvedValue({items:[]});api.saveHarness.mockResolvedValue(stored)})
describe('restricted Harness configuration',()=>{
 it('saves exact supported model revisions without runtime commands',async()=>{
  const w=editor();await flushPromises();const inputs=w.findAll('input');await inputs[0]!.setValue('my-runtime');await inputs[1]!.setValue('My runtime');await w.get('.bindings input').setValue(true);await w.get('form').trigger('submit');await flushPromises()
  expect(api.saveHarness).toHaveBeenCalledWith('my-runtime',{name:'My runtime',expected_revision:0,enabled:true,template_profile_id:'direct-template',provider_profile_ids:['local-model-v1']},'test-token');expect(w.emitted('changed')).toHaveLength(1);expect(w.text()).toContain('保存不会执行评测')
 })
 it('disables using the loaded revision and keeps conflict errors sanitized',async()=>{
  api.harnesses.mockResolvedValue({items:[stored]});const w=editor();await flushPromises();await w.get('li button').trigger('click');await w.get('.checkbox input').setValue(false);api.saveHarness.mockRejectedValue(new Error('private-sentinel'));await w.get('form').trigger('submit');await flushPromises()
  expect(api.saveHarness.mock.calls[0]![1]).toMatchObject({expected_revision:1,enabled:false});expect(w.get('[role=alert]').text()).toContain('重新读取');expect(w.text()).not.toContain('private-sentinel')
 })
 it('blocks stale bindings after a model revision disappears',async()=>{
  api.harnesses.mockResolvedValue({items:[stored]});api.options.mockResolvedValue({model_controls:[],harness_templates:[{...preset,supported_provider_profile_ids:['local-model-v2']}]});const w=editor();await flushPromises();await w.get('li button').trigger('click');expect(w.get('[role=alert]').text()).toContain('绑定已失效');expect(w.get('form button').attributes('disabled')).toBeDefined();await w.get('form').trigger('submit');expect(api.saveHarness).not.toHaveBeenCalled()
 })
 it('uses English and discards late responses after unmount',async()=>{
  preferences.language='en';let done!:(v:unknown)=>void;api.harnesses.mockReturnValue(new Promise(r=>{done=r}));const w=editor();expect(w.text()).toContain('Local runtime configurations');w.unmount();done({items:[stored]});await flushPromises();expect(w.emitted('changed')).toBeUndefined()
 })
})

 it('uses browser Unicode-sets patterns that accept legal IDs and reject malformed IDs', async () => {
   const wrapper = editor(); await flushPromises()
   const fields = wrapper.findAll('input[pattern]')
   expect(fields.length).toBeGreaterThan(0)
   for (const field of fields) {
     const pattern = new RegExp(`^(?:${field.attributes('pattern')})$`, 'v')
     expect(pattern.test('uat-valid-123')).toBe(true)
     for (const invalid of ['Invalid', '-bad', 'bad space', 'bad/key', 'a'.repeat(Number(field.attributes('maxlength')) + 1)]) expect(pattern.test(invalid)).toBe(false)
   }
 })
