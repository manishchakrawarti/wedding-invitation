Optional: your own licensed photos for the live demos.

  demo/<lang>/bride.jpg, groom.jpg, family.jpg   one language (e.g. demo/en/)
  demo/bride.jpg, groom.jpg, family.jpg          every language

<role>.jpg files are enhanced automatically (face framing, studio finish, vibrant).
<role>.ready.jpg files are used exactly as they are (e.g. the couple frame in en/ and hi/).
Changing a file updates the demo on the next server restart.

scripts/make_demo_family_ai.py creates a photorealistic family photo (couple + parents)
from bride.jpg and groom.jpg once GEMINI_API_KEY is set.

Only use photos you have the rights to. Without files here, demos use illustrated portraits.
