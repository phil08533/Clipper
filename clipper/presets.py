"""Ready-made campaign workflows. Picking one fills in every campaign setting, so nothing needs customising."""

RANDOM_SCHEDULE = {"schedule_mode": "random", "posts_min": 1, "posts_max": 3, "min_gap_minutes": 120,
                   "window_start": 10, "window_end": 22}

PRESETS = [
    {
        "key": "mythology",
        "name": "Mythology & Folklore",
        "tagline": "Myths and legends from around the world, told as gripping short stories.",
        "prompt_name": "Mythology & Folklore",
        "prompt": """Retell one traditional myth or folk legend as a gripping short story.
The topic tells you which legend; if it is open, choose a well-known myth from any culture related to {niche}.
Open with the most shocking or eerie moment of the legend, then tell what happened in order, and land on its twist or consequence.
Name the culture the story comes from in the first two scenes.
Retell the traditional version faithfully. Do not invent new events, characters or quotes.
Narration style: a campfire storyteller, vivid and plain-spoken, short sentences, present tense where it heightens tension.""",
        "config": {
            "niche": "world mythology and folklore",
            "visual_style": "dark fantasy oil painting, dramatic chiaroscuro lighting, mythic atmosphere, rich texture, highly detailed",
            "duration": 50, "scenes": 7, "caption_words": 3, "caption_position": "middle",
            "extra_hashtags": "#mythology #folklore #legends",
            "topics": [
                "The binding of Fenrir (Norse)", "Medusa's origin (Greek)", "The Wendigo (Algonquian)", "Kuchisake-onna, the slit-mouthed woman (Japanese)",
                "Anansi steals the sky god's stories (Akan)", "Orpheus and Eurydice (Greek)", "Baba Yaga's hut (Slavic)", "La Llorona (Mexican)",
                "Thor's fishing trip for the World Serpent (Norse)", "The Banshee (Irish)", "Pandora's jar (Greek)", "Izanagi in the underworld (Japanese)",
                "The Minotaur and the labyrinth (Greek)", "Loki and the death of Baldr (Norse)", "The Kraken (Scandinavian)", "Bloody Mary's mirror (British)",
                "Gilgamesh and the plant of immortality (Mesopotamian)", "The Nuckelavee (Orcadian)", "Arachne's contest with Athena (Greek)", "The Yuki-onna (Japanese)",
                "Sun Wukong vs the Jade Emperor (Chinese)", "The Selkie wife (Scottish)", "Icarus and Daedalus (Greek)", "Ragnarök (Norse)",
                "The Rainbow Serpent (Aboriginal Australian)", "The Headless Horseman (American)", "Persephone and the pomegranate (Greek)", "The Golem of Prague (Jewish)",
                "The Tanuki teakettle (Japanese)", "Ra's nightly journey through the underworld (Egyptian)", "Sisyphus and his boulder (Greek)", "The Pied Piper of Hamelin (German)",
                "Maui slows the sun (Polynesian)", "The Krampus (Alpine)", "Tantalus' punishment (Greek)", "The Draugr (Norse)",
                "Hou Yi shoots down the nine suns (Chinese)", "The Fox wife, Kitsune (Japanese)", "The Wild Hunt (European)", "Cú Chulainn's last stand (Irish)",
            ],
        },
    },
    {
        "key": "horror",
        "name": "Short Horror Stories",
        "tagline": "Original two-minute-campfire horror with a twist ending.",
        "prompt_name": "Short Horror Stories",
        "prompt": """Write an original, unsettling horror micro-story.
Use the topic as the seed idea; if it is open, invent a fresh premise in the spirit of {niche}.
Tell it in first person, as if it really happened to the narrator. Start in the middle of something wrong.
Build dread with specific, ordinary details. No gore; fear comes from implication.
The final scene must deliver a twist that recontextualises the story, in one short sentence.
Fiction only: never reference real crimes, real victims or real people.""",
        "config": {
            "niche": "psychological and supernatural horror",
            "visual_style": "eerie cinematic still, low-key lighting, desaturated colours, fog, film grain, unsettling composition, no people's faces visible",
            "duration": 55, "scenes": 7, "caption_words": 2, "caption_position": "middle",
            "extra_hashtags": "#horrorstory #scary #creepy",
            "topics": [
                "a voicemail from yourself, recorded tomorrow", "the house across the street has your lights on", "an extra step on the basement stairs",
                "a lost hiker's trail camera footage", "your reflection blinks a second late", "the night-shift security cameras at an empty mall",
                "a baby monitor picking up a second voice", "a hotel room that isn't on the floor plan", "the neighbour who mows his lawn at 3am",
                "a road trip where every exit sign says the same town", "the smart speaker that answers questions nobody asked",
                "a childhood photo with someone you don't remember", "the lighthouse keeper's last log entry", "a door in the woods with a doorbell",
                "a dating app match who knows too much", "the elevator that stops at floor 13", "a GPS voice that starts giving directions home… to a different home",
                "the knock that comes from inside the closet", "an antique doll that changes position overnight", "a radio station that only plays at 3:33am",
                "the last passenger on the night bus", "a rental cabin with locks on the outside of the doors", "your dog won't stop staring at the corner",
                "a text from your phone number", "the snowman that keeps getting closer", "the photocopier at work prints a face",
                "an abandoned hospital's patient list includes your name", "the ice cream truck in winter", "footprints in the snow that end at your window",
                "the forest that has no birdsong",
            ],
        },
    },
    {
        "key": "what_if",
        "name": "What If…?",
        "tagline": "Big hypothetical scenarios explained step by step.",
        "prompt_name": "What If",
        "prompt": """Explain one dramatic hypothetical scenario about {niche}.
Use the topic as the question; if it is open, choose a fresh "what if" that would make someone stop scrolling.
Open by stating the scenario as a vivid moment ("It's 3pm and suddenly…").
Walk through the consequences in time order: the first seconds, hours, days, years. Each scene escalates.
Base it on real science and say "scientists think" or "probably" where things are uncertain.
End with the most surprising consequence and a one-line question for the comments.""",
        "config": {
            "niche": "science, space and nature",
            "visual_style": "epic cinematic concept art, photorealistic, wide angle, volumetric light, dramatic sky, highly detailed",
            "duration": 50, "scenes": 7, "caption_words": 3, "caption_position": "middle",
            "extra_hashtags": "#whatif #science #space",
            "topics": [
                "What if the Moon disappeared?", "What if Earth stopped spinning for one second?", "What if you fell into a black hole?",
                "What if all insects vanished?", "What if the oceans dried up?", "What if humans could photosynthesise?",
                "What if Earth had rings like Saturn?", "What if the Sun turned into a black hole?", "What if a supervolcano erupted today?",
                "What if we drilled through the centre of the Earth?", "What if it rained for a whole year?", "What if gravity doubled?",
                "What if the dinosaurs never went extinct?", "What if Earth was twice as big?", "What if a rogue planet passed through the solar system?",
                "What if humans stopped sleeping?", "What if all the ice on Earth melted?", "What if Earth's magnetic field disappeared?",
                "What if you lived on Mars for a year?", "What if a sun-sized star replaced Jupiter?", "What if oxygen levels doubled?",
                "What if the internet disappeared forever?", "What if Earth had two suns?", "What if every volcano erupted at once?",
                "What if the speed of light was 100 km/h?", "What if humans lived for 500 years?", "What if a meteor hit the ocean?",
                "What if Antarctica was green again?", "What if the Earth was flat?", "What if we could see infrared?",
            ],
        },
    },
    {
        "key": "history_pov",
        "name": "A Day in History (POV)",
        "tagline": "\"You\" live a day as someone from history — immersive and specific.",
        "prompt_name": "A Day in History",
        "prompt": """Write an immersive second-person script: "You are…" a specific ordinary person on a specific day in history, related to {niche}.
Use the topic as the role and era.
Open with a sensory detail of waking up or arriving. Then move through the day hour by hour: food, work, dangers, beliefs, money.
Every scene needs one concrete, true historical detail. Only include details you are confident are historically accurate;
prefer common, well-documented facts over obscure claims, and never invent quotes or statistics.
End with how the day ends and one surprising fact about how long people like you usually lived.""",
        "config": {
            "niche": "everyday life through history",
            "visual_style": "historically accurate painterly scene, natural light, documentary realism, period costume and architecture, highly detailed",
            "duration": 55, "scenes": 7, "caption_words": 3, "caption_position": "lower",
            "extra_hashtags": "#history #povhistory #historyfacts",
            "topics": [
                "a Roman legionary on Hadrian's Wall, 122 AD", "an Egyptian pyramid worker at Giza, 2560 BC", "a medieval peasant during harvest, England 1300",
                "a Viking trader arriving in Constantinople, 950 AD", "a London child during the Great Fire, 1666", "a samurai's servant in Edo Japan, 1700",
                "a sailor on Magellan's voyage, 1520", "a factory child in Manchester, 1830", "a Pompeii baker on the morning of the eruption, 79 AD",
                "a Mongol scout in Genghis Khan's army, 1220", "a gladiator's first fight at the Colosseum, 80 AD", "a medieval monk copying manuscripts, 1150",
                "a passenger in steerage on the Titanic, 1912", "a gold-rush miner in California, 1849", "a plague doctor in Venice, 1630",
                "an Aztec merchant in Tenochtitlan, 1500", "a Spartan boy entering the agoge, 450 BC", "a lamplighter in Victorian London, 1880",
                "a Silk Road camel driver in Samarkand, 1300", "a soldier in a WWI trench, 1916", "a Byzantine chariot racing fan, 530 AD",
                "a cowboy on a cattle drive, Texas 1870", "a medieval castle cook, France 1250", "a scribe in ancient Babylon, 1750 BC",
                "a whaler out of Nantucket, 1820", "a Renaissance painter's apprentice in Florence, 1500", "an Inca chasqui messenger, 1500",
                "a stagecoach driver in the Old West, 1865", "a Chinese imperial exam candidate, 1400", "a telegraph operator during the Civil War, 1863",
            ],
        },
    },
    {
        "key": "series",
        "name": "Original Story Series",
        "tagline": "An ongoing fantasy saga in your own world — every video is the next episode.",
        "prompt_name": "Story Series Episode",
        "prompt": """Write the next episode of an ongoing short-form fantasy series in the world of {niche}.
Follow the story world and the previous episodes exactly: same names, places, rules and unresolved threads.
Each episode is self-contained enough to follow, but advances the main plot by one clear step.
Open with a one-line recap hook, then one tense scene, and end on a cliffhanger that makes viewers want the next part.
Introduce at most one new character per episode.""",
        "config": {
            "niche": "the Hollow Kingdom",
            "visual_style": "painterly dark fantasy illustration, consistent colour palette of deep blues and amber, cinematic framing, highly detailed",
            "duration": 50, "scenes": 6, "caption_words": 3, "caption_position": "middle",
            "extra_hashtags": "#fantasy #story #series",
            "topics": [],
            "series_bible": """The Hollow Kingdom is a kingdom built inside the hollow trunk of a dead world-tree so large that cities hang from its inner walls on chains.
Light comes only from amber lanterns fed by sap that is running out.
Main character: Wren, 17, a lantern-lighter's apprentice who can hear the tree whispering — something no one else can.
Mentor: Old Haskel, the last lantern-master, gruff, hiding that he once heard the whispers too.
Antagonist: the Sapwarden Order, who ration the sap and punish anyone who speaks of the whispers.
Mystery: the whispers say the tree is not dead — it is sleeping, and something is trying to wake it.
Tone: wonder with creeping dread. Each episode title starts with "Part N:".""",
        },
    },
    {
        "key": "insects",
        "name": "Insects & Bugs",
        "tagline": "The strangest real abilities of insects and spiders, up close.",
        "prompt_name": "Insects & Bugs",
        "prompt": """Make a short video about one real insect, spider or other bug and its most astonishing ability or behaviour, related to {niche}.
The topic names the creature; if it is open, pick a remarkable, well-documented one.
Open with the most surprising fact as a hook ("This beetle fires boiling chemicals from its rear").
Then explain how it works, why it evolved, and one vivid detail of it in action. End with a question for the comments.
Only state facts that are well established in biology. If a number is uncertain, say "about" or leave it out.
Never invent studies, quotes or record figures. Tone: amazed but precise, like a nature documentary narrator.""",
        "config": {
            "niche": "insects, spiders and other bugs",
            "visual_style": "extreme macro photography, shallow depth of field, crisp detail, natural light, dewdrops, nature documentary still",
            "duration": 45, "scenes": 6, "caption_words": 3, "caption_position": "lower",
            "extra_hashtags": "#insects #bugs #nature",
            "topics": [
                "the bombardier beetle's boiling chemical spray", "leafcutter ants farming fungus", "the trap-jaw ant's record-fast bite",
                "the orchid mantis disguised as a flower", "honeybees' waggle dance", "the monarch butterfly migration",
                "the zombie-ant fungus (Ophiocordyceps)", "tardigrades surviving space", "the peacock spider's courtship dance",
                "dragonflies, the deadliest hunters", "army ant living bridges", "the diving bell spider's underwater air bubble",
                "the jewel wasp that turns cockroaches into zombies", "fireflies' synchronised flashing", "dung beetles navigating by the Milky Way",
                "the Japanese giant hornet vs honeybee heat ball", "termite mounds' natural air-conditioning", "the stick insect that can clone itself",
                "the Goliath birdeater tarantula", "the water strider walking on water", "cicadas that wait 17 years underground",
                "the assassin bug that wears its victims", "the atlas moth that never eats", "the froghopper, champion jumper",
                "ant-mimicking jumping spiders", "the Portia spider that plans its attacks", "the hercules beetle's strength",
                "the mayfly that lives for one day", "the honeypot ants storing food in their bodies", "the silk of the Darwin's bark spider",
                "the cockroach that can live without its head", "the praying mantis' 3D vision", "the glasswing butterfly's transparent wings",
                "the botfly's strange life cycle", "the ladybird's reflex bleeding", "the trapdoor spider's ambush",
            ],
        },
    },
    {
        "key": "animals",
        "name": "Animal Kingdom",
        "tagline": "Astonishing animal abilities and behaviours, told like a wildlife documentary.",
        "prompt_name": "Animal Kingdom",
        "prompt": """Make a short video about one real animal and its most astonishing ability, behaviour or survival trick, related to {niche}.
The topic names the animal and angle; if it is open, pick a remarkable, well-documented one.
Open with the single most surprising fact as a hook. Then show the ability in action, explain how it works,
and why it helps the animal survive. End with a question for the comments.
Only state facts that are well established. Use "about" for approximate numbers, and never invent studies, quotes or records.
Tone: a warm, gripping wildlife-documentary narrator. Avoid graphic descriptions of injury.""",
        "config": {
            "niche": "wild animals and their abilities",
            "visual_style": "award-winning wildlife photography, telephoto lens, golden hour light, natural habitat, sharp focus, documentary realism",
            "duration": 45, "scenes": 6, "caption_words": 3, "caption_position": "lower",
            "extra_hashtags": "#animals #wildlife #nature",
            "topics": [
                "the octopus's three hearts and blue blood", "the mantis shrimp's punch", "the axolotl regrowing its limbs",
                "the peregrine falcon's 300 km/h dive", "elephants mourning their dead", "the pistol shrimp's sonic bubble",
                "the immortal jellyfish", "crows solving puzzles and remembering faces", "the arctic tern's pole-to-pole migration",
                "the pangolin's armour", "the platypus's electric sense", "the wood frog that freezes solid and thaws",
                "the cuttlefish's living camouflage", "humpback whales' bubble-net fishing", "the cheetah's acceleration",
                "the naked mole-rat that barely ages", "dolphins calling each other by name", "the sloth's slow-motion life",
                "the hummingbird's heartbeat", "the archerfish shooting water at insects", "the lyrebird that copies chainsaws",
                "sea otters holding hands while sleeping", "the electric eel's shocks", "the snow leopard's tail",
                "the mimic octopus impersonating other animals", "honey badgers' toughness", "the Greenland shark that lives 400 years",
                "the gecko walking on ceilings", "the owl's silent flight", "the emperor penguin's winter huddle",
                "the bar-tailed godwit's non-stop flight", "the chameleon's tongue", "the beaver as ecosystem engineer",
                "the anglerfish's glowing lure", "the kangaroo's pouch and joey", "the hippo's 'blood sweat' sunscreen",
                "the wolf pack's hunting strategy", "the bowerbird's decorated courtship stage", "the giraffe's blue tongue and heart",
            ],
        },
    },
]

PRESETS.sort(key=lambda p: p["key"] == "series")  # keep the series workflow last in the picker
PRESETS_BY_KEY = {p["key"]: p for p in PRESETS}


def summary():
    """Short list for the UI."""
    return [{
        "key": p["key"], "name": p["name"], "tagline": p["tagline"],
        "prompt_name": p["prompt_name"], "prompt": p["prompt"],
        "config": {**RANDOM_SCHEDULE, **p["config"]},
    } for p in PRESETS]
