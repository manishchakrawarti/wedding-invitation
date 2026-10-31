Optional: your own licensed photos for the live demos.

  demo/bride.jpg, groom.jpg, family.jpg          every language (current setup)
  demo/<lang>/bride.jpg, groom.jpg, family.jpg   override for one language (e.g. demo/ta/)

<role>.jpg files are enhanced automatically (face framing, studio finish, vibrant).
<role>.ready.jpg files are used exactly as they are (e.g. family.ready.jpg, the couple frame).
Changing a file updates the demos on the next server restart.

New AI cast (new bride & groom faces, father, mother, brother, sister, kids + family photo):
  set GEMINI_API_KEY in .env, then run: python scripts/make_demo_cast_ai.py

Only use photos you have the rights to. Without files here, demos use illustrated portraits.
