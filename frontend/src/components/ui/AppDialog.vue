<script setup>
// Squelette commun des modales de l'app : Dialog de shadcn-vue (focus bloqué dans la modale et
// rendu à la fermeture, Échap, clic à l'extérieur, accessibilité), la boîte visible restant
// celle de chaque modale (slot) avec son propre CSS.
//
// Usage : <AppDialog title="Déplacer" @close="…"><div class="modal-box">…</div></AppDialog>
//
// Choix de mise en page (voir DialogContent) :
// - le conteneur couvre l'écran en flex centré, SANS transform : la Dialog de shadcn se centre
//   avec translate(-50%), ce qui ferait de lui le repère de tout élément `position: fixed`
//   de la modale (confirmations internes, etc.) au lieu de l'écran ;
// - un clic à côté de la boîte tombe donc sur ce conteneur (pas sur le voile) : on le détecte
//   nous-mêmes (onBackdropPointerDown/onBackdropClick). Il laissait auparavant passer les clics
//   (pointer-events: none, sauf sur la boîte) ; sous Edge 153 (Windows), les modales ne
//   répondaient plus à la souris, seulement au clavier. On ne dépend plus de cette astuce.
import { Dialog, DialogContent, DialogTitle } from '@/components/shadcn/dialog'

const props = defineProps({
  // Nom de la modale pour les lecteurs d'écran — le titre visible reste dans la boîte.
  title: { type: String, required: true },
  // false : ni Échap ni clic à l'extérieur ne ferment (ex. pendant un traitement en cours).
  dismissible: { type: Boolean, default: true },
  // false : Échap ferme, mais pas un clic à l'extérieur (formulaires longs).
  closeOnOutsideClick: { type: Boolean, default: true },
})
const emit = defineEmits(['close'])

function onOpenChange(open) {
  if (!open) emit('close')
}
// Éléments de l'app rendus dans <body> mais qui "appartiennent" à la modale : la liste de
// suggestions d'AutocompleteInput, les menus/popovers/infobulles shadcn ouverts depuis elle.
function onInteractOutside(e) {
  const t = e.target
  if (t?.closest?.('.autocomplete-list, [data-slot$="-content"]')) { e.preventDefault(); return }
  if (!props.dismissible || !props.closeOnOutsideClick) e.preventDefault()
}
// Clic sur le fond (le conteneur lui-même, pas la boîte) : ferme, sauf si la sélection de
// texte a commencé dans la boîte (appui dedans, relâché à côté).
let downOnBackdrop = false
function onBackdropPointerDown(e) {
  downOnBackdrop = e.target === e.currentTarget
}
function onBackdropClick(e) {
  if (!downOnBackdrop || e.target !== e.currentTarget) return
  downOnBackdrop = false
  if (props.dismissible && props.closeOnOutsideClick) emit('close')
}
function onEscape(e) {
  if (!props.dismissible) e.preventDefault()
}
// Focus initial : le champ marqué autofocus s'il y en a un (l'attribut seul n'agit pas sur un
// contenu monté dynamiquement), sinon le comportement par défaut de Reka (premier élément
// focalisable).
function onOpenAutoFocus(e) {
  const target = e.target?.querySelector?.('[autofocus]')
  if (target) {
    e.preventDefault()
    target.focus()
  }
}
// Focus à la fermeture : Reka le rend à l'élément qui l'avait avant l'ouverture. S'il n'existe
// plus (élément d'un menu déjà refermé, ex. « Supprimer » d'un menu ⋮ qui ouvre une
// confirmation), le focus tomberait sur <body> — hors de la modale parente encore ouverte,
// dont Échap et Tab ne répondraient plus au clavier. On le ramène alors dans la Dialog ouverte
// la plus haute.
function onCloseAutoFocus() {
  setTimeout(() => {
    if (document.activeElement && document.activeElement !== document.body) return
    const open = [...document.querySelectorAll('[data-slot="dialog-content"][data-state="open"]')].pop()
    open?.focus()
  })
}
</script>

<template>
  <Dialog :open="true" @update:open="onOpenChange">
    <DialogContent
      :show-close-button="false"
      :aria-describedby="undefined"
      class="top-0 left-0 inset-0 flex h-full w-full max-w-none translate-x-0 translate-y-0 items-center justify-center gap-0 rounded-none border-0 bg-transparent p-4 shadow-none sm:max-w-none"
      @interact-outside="onInteractOutside"
      @escape-key-down="onEscape"
      @open-auto-focus="onOpenAutoFocus"
      @close-auto-focus="onCloseAutoFocus"
      @pointerdown="onBackdropPointerDown"
      @click="onBackdropClick"
    >
      <DialogTitle class="sr-only">{{ title }}</DialogTitle>
      <slot />
    </DialogContent>
  </Dialog>
</template>
