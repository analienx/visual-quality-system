# World countries for account-free Shape Map

A generic derivative of TopoJSON world-atlas v2 countries-110m, from Natural Earth. Only the United States of America geography name was changed to United States to match the Contoso Dim Store.Country dimension. Other names and arcs are unchanged.

Original project: https://github.com/topojson/world-atlas
License: WORLD_ATLAS_LICENSE.txt (ISC).
No business data, credentials, or PBIP content is included.

## No-Antarctica variant for dashboard readability
The derivative world-countries-110m-without-antarctica.topojson omits only Antarctica from the 110m country topology; the geography arcs, five Contoso keys and other country features are identical. The map uses a fixed, commit-pinned URL to keep geography stable. In Power BI Desktop the large Antarctica shape previously occupied too much map tile space. This is a user experience trial, not an alteration to semantic model or sales values.
