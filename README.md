# notemd

Pikamuistiinpanosovellus Linuxille (Python + GTK3). Avaa pienen tumman ikkunan pikanäppäimellä, kirjoitat muistiinpanon ja se tallentuu aikaleimalla Markdown-tiedostoon, jäsenneltynä kategorioittain.

## Ominaisuudet
- Pieni konsolityylinen ikkuna, viisi viimeisintä muistiinpanoa näkyvillä
- Kategoriat (luonti nappina, pikavalinta Ctrl+1…9)
- Kiinnitys (📌), muokkaus, poisto, haku ja raahaus kategorioiden välillä "kaikki muistiinpanot" -ikkunassa
- Suomalainen päivämäärä viikonpäivällä: `ti 17.11.2026 17:50:59`

## Näppäimet
| Näppäin | Toiminto |
|---|---|
| Enter | rivinvaihto |
| Enter Enter (nopeasti) / Ctrl+Enter | tallenna |
| Esc | sulje (varoittaa tallentamattomasta tekstistä) |

## Vaatimukset
Python 3, `python3-gi`, GTK 3 (`gir1.2-gtk-3.0`), GdkPixbuf SVG-tuki (`librsvg2-common`).

## Asennus
```sh
./install.sh
```
Lisää sovellusvalikkoon launcherin ja kuvakkeen. Pikanäppäin asetetaan työpöydän omista asetuksista (KDE: Järjestelmäasetukset → Pikanäppäimet → Lisää komento): `/polku/notemd.py`.

## Tallennus
Muistiinpanot tallennetaan tiedostoon `~/Documents/InstaNote/muistiinpanot.md`:

```
# Yleinen

## ti 17.11.2026 17:50:59

teksti

# Työ
...
```
Tiedosto on tavallista Markdownia, ja kiinnitetyn muistiinpanon otsikon perässä on 📌.
