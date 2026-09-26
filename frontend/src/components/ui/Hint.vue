<script setup>
// Infobulle d'un bouton à icône seule (remplace l'attribut title="…") : Tooltip de shadcn-vue,
// qui apparaît vite au survol ET au focus clavier, contrairement à la bulle native. Pose aussi
// aria-label sur le bouton — son seul nom lisible par un lecteur d'écran.
//
// Usage : <Hint label="Modifier"><button …><SvgIcon …/></button></Hint>. Le contenu doit être
// UN élément (pas un composant sans racine unique). Pour un bouton qui ouvre déjà un menu ou
// un popover, envelopper le déclencheur : <Hint label="…"><DropdownMenuTrigger as-child>…
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/shadcn/tooltip'

defineProps({
  label: { type: String, default: '' },
  side: { type: String, default: 'top' },
})
</script>

<template>
  <Tooltip :disabled="!label">
    <TooltipTrigger as-child :aria-label="label || undefined">
      <slot />
    </TooltipTrigger>
    <TooltipContent :side="side">{{ label }}</TooltipContent>
  </Tooltip>
</template>
