# brand-src: SVG sources for gapfix6 brand-asset PNG renditions

These SVGs are the sources for the three PNG media objects that
`gapfix6-brand-kb.py` expects under
`mocks/data/agency-directus-assets/dam/cedar-and-co-coffee/`:

- cedar-logo-cream.svg -> cedar-logo-cream.png (512 wide)
- cedar-wordmark-horizontal.svg -> cedar-wordmark-horizontal.png (1600 wide)
- cedar-summer-web-banner.svg -> cedar-summer-web-banner.png (2400 wide)

Render OFF-BOX (the mocks container has no fonts; same convention as
`fetch-dam-objects.py` logo PNGs) with sharp:

    node -e "const sharp=require('sharp');
      sharp('cedar-logo-cream.svg',{density:300}).resize({width:512}).png().toFile('cedar-logo-cream.png')"

Then copy the PNGs into `mocks/data/agency-directus-assets/dam/cedar-and-co-coffee/`
on the box before running `gapfix6-brand-kb.py` (it fails loud when an object
is missing so a dangling dam_assets row is never created).
