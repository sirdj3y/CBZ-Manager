// Passkeys côté navigateur (voir backend/services/passkeys.py) : @simplewebauthn/browser
// dialogue avec l'appareil (Face ID, Touch ID, Windows Hello, gestionnaire de mots de passe).
import { browserSupportsWebAuthn, startAuthentication, startRegistration } from '@simplewebauthn/browser'
import { passkeysApi } from '../api/passkeys'

/**
 * État des passkeys pour la page courante :
 *  - usable : activées ET page ouverte depuis l'adresse publique (une passkey est liée à ce
 *    domaine : via l'IP locale du NAS, le navigateur la refuserait) ;
 *  - origin : l'adresse publique, pour inviter à l'utiliser quand on n'y est pas.
 */
export async function passkeyStatus() {
  try {
    const { data } = await passkeysApi.status()
    const supported = browserSupportsWebAuthn()
    return {
      enabled: data.enabled,
      origin: data.origin,
      usable: data.enabled && supported && data.origin === window.location.origin,
    }
  } catch {
    return { enabled: false, origin: null, usable: false }
  }
}

// L'utilisateur a fermé ou refusé la demande de l'appareil : pas une erreur à afficher.
export function isCancelled(e) {
  return e?.name === 'NotAllowedError' || e?.name === 'AbortError'
}

// Message affichable pour une erreur de passkey. Cas fréquent : l'appareil a DÉJÀ une passkey
// pour ce compte, synchronisée depuis un autre appareil (trousseau iCloud entre Mac et iPhone,
// gestionnaire Google, 1Password…) — il refuse alors d'en créer une seconde (InvalidStateError,
// d'après la liste excludeCredentials envoyée par le serveur). Elle est déjà utilisable.
export function passkeyErrorMessage(e, fallback) {
  if (e?.name === 'InvalidStateError' || e?.code === 'ERROR_AUTHENTICATOR_PREVIOUSLY_REGISTERED') {
    return "Cet appareil a déjà une passkey pour ce compte, sans doute synchronisée depuis un autre appareil (trousseau iCloud, gestionnaire de mots de passe). Elle permet déjà de vous connecter."
  }
  if (e?.response?.data?.detail) return e.response.data.detail
  return e?.message ? `${fallback} : ${e.message}` : fallback
}

export async function registerPasskey(name) {
  const { data } = await passkeysApi.registerOptions()
  const credential = await startRegistration({ optionsJSON: data.options })
  const { data: created } = await passkeysApi.registerVerify({ challenge_id: data.challenge_id, name, credential })
  return created
}

export async function loginWithPasskey() {
  const { data } = await passkeysApi.loginOptions()
  const credential = await startAuthentication({ optionsJSON: data.options })
  const { data: status } = await passkeysApi.loginVerify({ challenge_id: data.challenge_id, credential })
  return status
}

// Nom proposé par défaut pour une nouvelle passkey, d'après l'appareil.
export function defaultPasskeyName() {
  const ua = navigator.userAgent
  if (/iPhone/.test(ua)) return 'iPhone'
  if (/iPad/.test(ua)) return 'iPad'
  if (/Android/.test(ua)) return 'Android'
  if (/Macintosh/.test(ua)) return 'Mac'
  if (/Windows/.test(ua)) return 'Windows'
  return 'Passkey'
}
