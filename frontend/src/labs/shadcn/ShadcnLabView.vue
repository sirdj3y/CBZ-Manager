<script setup>
// Vitrine shadcn-vue (/labo/shadcn, non liée dans le menu) — les composants de
// src/components/shadcn/ sur les vraies données de la bibliothèque. Lecture seule : rien
// n'est enregistré.
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { BookOpen, Ellipsis, Info, Pencil, Search, SlidersHorizontal } from '@lucide/vue'
import AppLayout from '../../components/layout/AppLayout.vue'
import { libraryApi } from '../../api/library'
import { Badge } from '@/components/shadcn/badge'
import { Button } from '@/components/shadcn/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/shadcn/card'
import {
  CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList,
} from '@/components/shadcn/command'
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/shadcn/dialog'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/shadcn/dropdown-menu'
import { Input } from '@/components/shadcn/input'
import { Label } from '@/components/shadcn/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/shadcn/select'
import { Separator } from '@/components/shadcn/separator'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/shadcn/sheet'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/shadcn/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/shadcn/tabs'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/shadcn/tooltip'

const router = useRouter()
const series = ref([])
const classifications = ref([])
const loading = ref(true)
const filter = ref('')
const classFilter = ref('toutes')

const editing = ref(null)   // série ouverte dans le dialogue d'édition (copie locale)
const editOpen = ref(false)
const saved = ref(false)
const detail = ref(null)    // série ouverte dans le panneau latéral
const sheetOpen = ref(false)
const searchOpen = ref(false)

onMounted(async () => {
  try {
    const [s, c] = await Promise.all([libraryApi.getSeries(), libraryApi.getClassifications()])
    series.value = s.data
    classifications.value = c.data
  } finally {
    loading.value = false
  }
})

const visible = computed(() => {
  const q = filter.value.trim().toLowerCase()
  return series.value
    .filter(s => classFilter.value === 'toutes' || s.classification === classFilter.value)
    .filter(s => !q || s.name.toLowerCase().includes(q) || s.writers.some(w => w.toLowerCase().includes(q)))
    .slice(0, 50)
})

function openEdit(s) {
  editing.value = { ...s, classification: s.classification || 'aucune' }
  saved.value = false
  editOpen.value = true
}

async function openDetail(s) {
  sheetOpen.value = true
  detail.value = { ...s, tomes: null }
  const { data } = await libraryApi.getSeriesDetail(s.id)
  if (detail.value?.id === s.id) detail.value = data
}

function goTo(s) {
  searchOpen.value = false
  router.push(`/series/${s.id}`)
}
</script>

<template>
  <AppLayout>
    <TooltipProvider :delay-duration="300">
      <main class="mx-auto w-full max-w-5xl px-5 py-6 text-foreground">
        <div class="mb-6 flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 class="font-[family-name:var(--font-display)] text-2xl uppercase tracking-wide">Labo — shadcn-vue</h1>
            <p class="mt-1 max-w-2xl text-sm text-muted-foreground">
              Essai des composants shadcn-vue avec les couleurs de l'app, sur ta vraie bibliothèque.
              Lecture seule : rien n'est enregistré. Change le thème clair/sombre pour voir le rendu.
            </p>
          </div>
          <Button variant="outline" @click="searchOpen = true">
            <Search /> Palette de démo
          </Button>
        </div>

        <Tabs default-value="series">
          <TabsList>
            <TabsTrigger value="series">Séries</TabsTrigger>
            <TabsTrigger value="composants">Composants</TabsTrigger>
          </TabsList>

          <!-- Tableau des séries : filtres, menu d'actions, infobulles -->
          <TabsContent value="series" class="mt-4">
            <Card>
              <CardHeader>
                <CardTitle>Séries</CardTitle>
                <CardDescription>
                  {{ loading ? 'Chargement…' : `${series.length} séries — 50 premières affichées` }}
                </CardDescription>
              </CardHeader>
              <CardContent class="space-y-4">
                <div class="flex flex-wrap gap-3">
                  <Input v-model="filter" placeholder="Filtrer par série ou scénariste…" class="max-w-xs" />
                  <Select v-model="classFilter">
                    <SelectTrigger class="w-52"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="toutes">Toutes les classifications</SelectItem>
                      <SelectItem v-for="c in classifications" :key="c" :value="c">{{ c }}</SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Série</TableHead>
                      <TableHead>Classification</TableHead>
                      <TableHead class="text-right">Albums</TableHead>
                      <TableHead>Scénario</TableHead>
                      <TableHead class="w-10" />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    <TableRow v-for="s in visible" :key="s.id">
                      <TableCell class="font-medium">
                        <button class="cursor-pointer hover:underline" @click="openDetail(s)">{{ s.name }}</button>
                      </TableCell>
                      <TableCell>
                        <Badge v-if="s.classification" variant="secondary">{{ s.classification }}</Badge>
                        <span v-else class="text-muted-foreground">—</span>
                      </TableCell>
                      <TableCell class="text-right tabular-nums">{{ s.tome_count }}</TableCell>
                      <TableCell class="max-w-56 truncate text-muted-foreground">
                        <Tooltip v-if="s.writers.length > 1">
                          <TooltipTrigger as-child><span>{{ s.writers[0] }} +{{ s.writers.length - 1 }}</span></TooltipTrigger>
                          <TooltipContent>{{ s.writers.join(', ') }}</TooltipContent>
                        </Tooltip>
                        <span v-else>{{ s.writers[0] || '—' }}</span>
                      </TableCell>
                      <TableCell>
                        <DropdownMenu>
                          <DropdownMenuTrigger as-child>
                            <Button variant="ghost" size="icon-sm" aria-label="Actions"><Ellipsis /></Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuLabel>{{ s.name }}</DropdownMenuLabel>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem @select="openDetail(s)"><Info /> Aperçu</DropdownMenuItem>
                            <DropdownMenuItem @select="openEdit(s)"><Pencil /> Éditer…</DropdownMenuItem>
                            <DropdownMenuItem @select="router.push(`/series/${s.id}`)"><BookOpen /> Ouvrir la fiche</DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </TableCell>
                    </TableRow>
                    <TableRow v-if="!loading && !visible.length">
                      <TableCell colspan="5" class="py-8 text-center text-muted-foreground">Aucune série ne correspond.</TableCell>
                    </TableRow>
                  </TableBody>
                </Table>
              </CardContent>
            </Card>
          </TabsContent>

          <!-- Catalogue des variantes -->
          <TabsContent value="composants" class="mt-4 space-y-4">
            <Card>
              <CardHeader><CardTitle>Boutons</CardTitle></CardHeader>
              <CardContent class="flex flex-wrap items-center gap-3">
                <Button>Principal</Button>
                <Button variant="secondary">Secondaire</Button>
                <Button variant="outline">Contour</Button>
                <Button variant="ghost">Discret</Button>
                <Button variant="destructive">Supprimer</Button>
                <Button variant="link">Lien</Button>
                <Button disabled>Désactivé</Button>
                <Tooltip>
                  <TooltipTrigger as-child><Button variant="outline" size="icon" aria-label="Réglages"><SlidersHorizontal /></Button></TooltipTrigger>
                  <TooltipContent>Infobulle au survol (remplace title="…")</TooltipContent>
                </Tooltip>
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle>Badges</CardTitle></CardHeader>
              <CardContent class="flex flex-wrap gap-2">
                <Badge>Nouveau</Badge>
                <Badge variant="secondary">Manga</Badge>
                <Badge variant="outline">CBZ</Badge>
                <Badge variant="destructive">Fichier introuvable</Badge>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </main>

      <!-- Dialogue d'édition (démo, rien n'est enregistré) -->
      <Dialog v-model:open="editOpen">
        <DialogContent v-if="editing">
          <DialogHeader>
            <DialogTitle>Éditer « {{ editing.name }} »</DialogTitle>
            <DialogDescription>Démonstration : Échap ferme, Tab reste dans le dialogue, le focus revient au menu.</DialogDescription>
          </DialogHeader>
          <div class="grid gap-4 py-2">
            <div class="grid gap-2">
              <Label for="lab-name">Nom</Label>
              <Input id="lab-name" v-model="editing.name" />
            </div>
            <div class="grid gap-2">
              <Label>Classification</Label>
              <Select v-model="editing.classification">
                <SelectTrigger class="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="aucune">Non classée</SelectItem>
                  <SelectItem v-for="c in classifications" :key="c" :value="c">{{ c }}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <p v-if="saved" class="text-sm text-muted-foreground">Démo : rien n'a été enregistré.</p>
          </div>
          <DialogFooter>
            <Button variant="outline" @click="editOpen = false">Annuler</Button>
            <Button @click="saved = true">Enregistrer</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <!-- Panneau latéral (équivalent du tiroir de métadonnées) -->
      <Sheet v-model:open="sheetOpen">
        <SheetContent class="w-full overflow-y-auto sm:max-w-md">
          <SheetHeader v-if="detail">
            <SheetTitle>{{ detail.name }}</SheetTitle>
            <SheetDescription>
              {{ detail.tome_count }} album(s)<template v-if="detail.classification"> · {{ detail.classification }}</template>
            </SheetDescription>
          </SheetHeader>
          <div v-if="detail" class="space-y-4 px-4 pb-6">
            <img v-if="detail.cover_url" :src="detail.cover_url" alt="" class="w-32 rounded-md border shadow-sm" />
            <div v-if="detail.writers?.length" class="text-sm"><span class="text-muted-foreground">Scénario : </span>{{ detail.writers.join(', ') }}</div>
            <div v-if="detail.pencillers?.length" class="text-sm"><span class="text-muted-foreground">Dessin : </span>{{ detail.pencillers.join(', ') }}</div>
            <Separator />
            <p v-if="!detail.tomes" class="text-sm text-muted-foreground">Chargement des albums…</p>
            <ul v-else class="space-y-1 text-sm">
              <li v-for="t in detail.tomes" :key="t.id" class="flex justify-between gap-3">
                <span class="truncate">{{ t.number ? `T${t.number} — ` : '' }}{{ t.title || t.filename }}</span>
                <Badge variant="outline" class="uppercase">{{ t.file_format }}</Badge>
              </li>
            </ul>
            <Button class="w-full" @click="router.push(`/series/${detail.id}`)">Ouvrir la fiche</Button>
          </div>
        </SheetContent>
      </Sheet>

      <!-- Palette de recherche ⌘K -->
      <CommandDialog v-model:open="searchOpen" title="Rechercher" description="Rechercher une série">
        <CommandInput placeholder="Nom de série, scénariste…" />
        <CommandList>
          <CommandEmpty>Aucun résultat.</CommandEmpty>
          <CommandGroup heading="Séries">
            <CommandItem
              v-for="s in series" :key="s.id"
              :value="`${s.name} ${s.writers.join(' ')}`"
              @select="goTo(s)"
            >
              <BookOpen />
              <span>{{ s.name }}</span>
              <span class="ml-auto text-xs text-muted-foreground">{{ s.tome_count }} alb.</span>
            </CommandItem>
          </CommandGroup>
        </CommandList>
      </CommandDialog>
    </TooltipProvider>
  </AppLayout>
</template>
