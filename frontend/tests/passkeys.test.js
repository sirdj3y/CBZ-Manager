import { describe, expect, it } from 'vitest'
import { passkeyErrorMessage } from '../src/utils/passkeys.js'

describe('passkeyErrorMessage', () => {
  it('passkey déjà présente sur l’appareil (synchronisée)', () => {
    expect(passkeyErrorMessage({ name: 'InvalidStateError' }, 'x')).toContain('déjà une passkey')
    expect(passkeyErrorMessage({ code: 'ERROR_AUTHENTICATOR_PREVIOUSLY_REGISTERED' }, 'x')).toContain('déjà une passkey')
  })
  it('message du serveur en priorité', () => {
    expect(passkeyErrorMessage({ response: { data: { detail: 'Demande expirée. Recommencez.' } } }, 'x')).toBe('Demande expirée. Recommencez.')
  })
  it('sinon le détail technique, pour pouvoir diagnostiquer', () => {
    expect(passkeyErrorMessage({ message: 'The operation is insecure.' }, 'Impossible')).toBe('Impossible : The operation is insecure.')
    expect(passkeyErrorMessage({}, 'Impossible')).toBe('Impossible')
  })
})
