import type { InjectionKey, Ref } from 'vue'

export type ProductMode = 'demo' | 'workspace' | 'unknown'
export const productModeKey: InjectionKey<Ref<ProductMode>> = Symbol('productMode')
