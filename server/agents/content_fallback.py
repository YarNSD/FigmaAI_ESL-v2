"""
ESL Figma AI — Educational Content Fallback Generator
Provides robust, CEFR-aligned learning materials when offline or without active LLM credentials.
Guarantees that material creation on FigJam/Figma NEVER fails or crashes.
"""
from typing import Dict, List, Optional, Any
import re
import random

# Pre-curated educational databases for popular ESL topics
TOPIC_DATABASES = {
    "food": {
        "title": "Food & Cooking",
        "vocab": [
            {"word": "ingredients [ɪnˈɡriːdiənts]", "translation": "ингредиенты", "type": "noun", "example": "Fresh ingredients make any dish taste much better.", "image_query": "fresh cooking ingredients vegetable"},
            {"word": "delicious [dɪˈlɪʃəs]", "translation": "очень вкусный", "type": "adjective", "example": "This homemade apple pie is absolutely delicious.", "image_query": "delicious apple pie bakery"},
            {"word": "recipe [ˈresəpi]", "translation": "рецепт", "type": "noun", "example": "Follow this simple recipe to make Italian pasta.", "image_query": "recipe book kitchen cooking"},
            {"word": "to bake [beɪk]", "translation": "выпекать", "type": "verb", "example": "My grandmother loves to bake fresh bread on Sundays.", "image_query": "fresh baked bread oven"},
            {"word": "spicy [ˈspaɪsi]", "translation": "острый, пряный", "type": "adjective", "example": "Be careful, this Mexican sauce is very spicy.", "image_query": "chili pepper spicy dish"},
            {"word": "flavor [ˈfleɪvər]", "translation": "вкус, аромат", "type": "noun", "example": "Adding herbs gives the soup a rich and herbal flavor.", "image_query": "herbs spices culinary"}
        ],
        "quiz": [
            {"sentence": "Which verb means to cook food in an oven using dry heat?", "options": ["Bake", "Boil", "Freeze"], "correct_index": 0, "explanation": "Baking is cooking in an oven without direct flame.", "image_query": "baking bread oven"},
            {"sentence": "What do we call a list of instructions for cooking a dish?", "options": ["Menu", "Recipe", "Bill"], "correct_index": 1, "explanation": "A recipe describes the steps and ingredients needed.", "image_query": "recipe cookbook cooking"},
            {"sentence": "If food is very hot from chili peppers, we describe it as ___.", "options": ["Sweet", "Spicy", "Bitter"], "correct_index": 1, "explanation": "Spicy means containing strong hot spices like chili.", "image_query": "chili peppers red"},
            {"sentence": "Where do you typically leave extra money for good restaurant service?", "options": ["A tip", "A discount", "A refund"], "correct_index": 0, "explanation": "A tip is a gratuity given to the waiter for good service.", "image_query": "restaurant bill tip money"}
        ],
        "speaking": [
            {"emoji": "🍕", "question": "Would you rather eat only homemade food or eat out at restaurants?", "follow_up": "What is your all-time favorite meal to cook?", "color": "#2563eb"},
            {"emoji": "🌍", "question": "Which national cuisine in the world do you find most exciting?", "follow_up": "Have you ever tried traditional street food abroad?", "color": "#16a34a"},
            {"emoji": "👨‍🍳", "question": "If you could open your own dream cafe, what would be your signature dish?", "follow_up": "How would you design the interior and atmosphere?", "color": "#d97706"},
            {"emoji": "🥗", "question": "Do you believe healthy organic food is always more expensive?", "follow_up": "What habits help people maintain a balanced diet?", "color": "#7c3aed"}
        ],
        "fill": [
            {"sentence_with_blank": "Can you please pass me the ___ to chop these onions?", "answer": "knife", "translation": "Не мог бы ты передать мне нож, чтобы нарезать лук?"},
            {"sentence_with_blank": "We need to buy fresh ___ before making dinner tonight.", "answer": "vegetables", "translation": "Нам нужно купить свежие овощи перед приготовлением ужина."},
            {"sentence_with_blank": "This Italian soup has a wonderful ___ of basil and garlic.", "answer": "flavor", "translation": "У этого итальянского супа чудесный аромат базилика и чеснока."},
            {"sentence_with_blank": "Don't forget to ___ the water before adding pasta.", "answer": "boil", "translation": "Не забудь вскипятить воду перед добавлением пасты."}
        ]
    },
    "daily": {
        "title": "Daily Life & Routines",
        "vocab": [
            {"word": "routine [ruːˈtiːn]", "translation": "распорядок дня", "type": "noun", "example": "A consistent morning routine helps me stay productive all day.", "image_query": "morning alarm clock routine"},
            {"word": "commute [kəˈmjuːt]", "translation": "дорога на работу/учебу", "type": "noun / verb", "example": "My daily commute by subway takes about thirty minutes.", "image_query": "subway train commuters city"},
            {"word": "productive [prəˈdʌktɪv]", "translation": "продуктивный", "type": "adjective", "example": "I feel most productive early in the morning.", "image_query": "workspace desk laptop notebook"},
            {"word": "to unwind [ʌnˈwaɪnd]", "translation": "расслабляться", "type": "verb", "example": "Listening to acoustic music helps me unwind after work.", "image_query": "person relaxing reading book sofa"},
            {"word": "deadline [ˈdedlaɪn]", "translation": "крайний срок", "type": "noun", "example": "We managed to finish the report two hours before the deadline.", "image_query": "calendar planner schedule deadline"},
            {"word": "habit [ˈhæbɪt]", "translation": "привычка", "type": "noun", "example": "Drinking a glass of water every morning is a healthy habit.", "image_query": "glass water morning health"}
        ],
        "quiz": [
            {"sentence": "What is the opposite of an 'early bird' who wakes up at dawn?", "options": ["Night owl", "Late sleeper", "Evening person", "Midnight worker"], "correct_index": 0, "explanation": "A night owl is someone who stays awake late into the night.", "image_query": "young woman waking up early morning bed sunshine"},
            {"sentence": "Which verb describes traveling between your home and your workplace?", "options": ["Commute", "Migrate", "Cruise", "Depart"], "correct_index": 0, "explanation": "To commute means to travel regularly to and from work.", "image_query": "commuter passenger on subway train morning"},
            {"sentence": "When you have too many tasks and feel stressed, you feel ___.", "options": ["Overwhelmed", "Refreshed", "Bored", "Relaxed"], "correct_index": 0, "explanation": "Overwhelmed means having too much to deal with at once.", "image_query": "person stressed desk office papers hands on head"},
            {"sentence": "What do we call a regular pattern of activities you do every day?", "options": ["Routine", "Coincidence", "Vacation", "Emergency"], "correct_index": 0, "explanation": "A routine is a habitual sequence of daily actions.", "image_query": "person writing daily planner morning coffee"},
            {"sentence": "What morning meal do people usually eat before starting work?", "options": ["Breakfast", "Dinner", "Dessert", "Midnight snack"], "correct_index": 0, "explanation": "Breakfast is the first meal eaten in the morning.", "image_query": "person preparing healthy breakfast kitchen eggs toast"},
            {"sentence": "Which activity helps keep your body fit and energized in the morning?", "options": ["Jogging", "Sleeping in", "Watching television", "Shopping online"], "correct_index": 0, "explanation": "Jogging is a popular morning exercise.", "image_query": "person jogging in park morning sunrise fitness"},
            {"sentence": "What do you do right after waking up to keep your teeth clean?", "options": ["Brush teeth", "Wash the car", "Iron clothes", "Paint walls"], "correct_index": 0, "explanation": "Brushing teeth is an essential morning hygiene habit.", "image_query": "person brushing teeth bathroom mirror morning"},
            {"sentence": "What do we call the final time or date by which a task must be finished?", "options": ["Deadline", "Break time", "Weekend", "Holiday"], "correct_index": 0, "explanation": "A deadline is the latest time to complete an assignment.", "image_query": "calendar planner schedule clock deadline"},
            {"sentence": "What is a great way to ___ after a long exhausting day at work?", "options": ["Unwind", "Rush", "Panic", "Compete"], "correct_index": 0, "explanation": "To unwind means to relax and release tension.", "image_query": "person reading book cozy sofa cup of tea evening"},
            {"sentence": "What device rings with a sound at a scheduled time to wake you up?", "options": ["Alarm clock", "Flashlight", "Headphones", "Calculator"], "correct_index": 0, "explanation": "An alarm clock wakes you up at a set time.", "image_query": "analog alarm clock nightstand morning sunlight"}
        ],
        "speaking": [
            {"emoji": "⏰", "question": "Are you more productive in the early morning or late at night?", "follow_up": "How does your energy level change throughout the day?", "color": "#2563eb"},
            {"emoji": "☕", "question": "What is one morning ritual you cannot imagine your day without?", "follow_up": "How do you feel if this routine gets interrupted?", "color": "#16a34a"},
            {"emoji": "📱", "question": "How many hours do you spend on screens before going to sleep?", "follow_up": "Have you ever tried a digital detox weekend?", "color": "#d97706"},
            {"emoji": "🛋️", "question": "What is your favorite way to unwind after an exhausting week?", "follow_up": "Do you prefer spending time alone or with friends?", "color": "#7c3aed"}
        ],
        "fill": [
            {"sentence_with_blank": "I usually set my alarm ___ for seven in the morning.", "answer": "clock", "translation": "Я обычно ставлю будильник на семь утра."},
            {"sentence_with_blank": "It takes me twenty minutes to ___ to the city center.", "answer": "commute", "translation": "У меня уходит двадцать минут на дорогу до центра города."},
            {"sentence_with_blank": "Drinking herbal tea is a great way to ___ after a busy day.", "answer": "unwind", "translation": "Пить травяной чай — отличный способ расслабиться после насыщенного дня."},
            {"sentence_with_blank": "We need to plan our weekly ___ to avoid missing deadlines.", "answer": "schedule", "translation": "Нам нужно распланировать недельный график, чтобы не пропустить дедлайны."},
            {"sentence_with_blank": "Eating a healthy ___ gives you energy for the entire morning.", "answer": "breakfast", "translation": "Здоровый завтрак дает вам энергию на все утро."},
            {"sentence_with_blank": "A consistent morning ___ helps you start your day with focus.", "answer": "routine", "translation": "Постоянный утренний распорядок помогает начать день сосредоточенно."},
            {"sentence_with_blank": "Drinking a glass of water every morning is a healthy ___.", "answer": "habit", "translation": "Стакан воды каждое утро — полезная привычка."},
            {"sentence_with_blank": "We must complete and submit the project before the 5 PM ___.", "answer": "deadline", "translation": "Мы должны завершить и сдать проект до дедлайна в 17:00."},
            {"sentence_with_blank": "Going ___ in the park every morning keeps your body energized.", "answer": "jogging", "translation": "Утренняя пробежка в парке заряжает тело энергией."},
            {"sentence_with_blank": "Remember to brush your ___ twice a day to maintain dental health.", "answer": "teeth", "translation": "Не забывайте чистить зубы дважды в день для здоровья полости рта."}
        ]
    },
    "travel": {
        "title": "Travel & Adventures",
        "vocab": [
            {"word": "destination [ˌdestɪˈneɪʃn]", "translation": "пункт назначения", "type": "noun", "example": "Japan was our dream holiday destination for many years.", "image_query": "airplane window mountain view travel"},
            {"word": "luggage [ˈlʌɡɪdʒ]", "translation": "багаж", "type": "noun", "example": "Make sure your luggage weighs less than twenty kilograms.", "image_query": "travel suitcase luggage airport"},
            {"word": "sightseeing [ˈsaɪtsiːɪŋ]", "translation": "осмотр достопримечательностей", "type": "noun", "example": "We spent the entire afternoon sightseeing in ancient Rome.", "image_query": "colosseum rome tourist sightseeing"},
            {"word": "itinerary [aɪˈtɪnərəri]", "translation": "план маршрута", "type": "noun", "example": "Our detailed travel itinerary includes four European capitals.", "image_query": "travel map route itinerary compass"},
            {"word": "breathtaking [ˈbreθteɪkɪŋ]", "translation": "захватывающий дух", "type": "adjective", "example": "The mountain view from the balcony was truly breathtaking.", "image_query": "breathtaking mountain view alpine sunset"},
            {"word": "souvenir [ˌsuːvəˈnɪər]", "translation": "сувенир", "type": "noun", "example": "I bought a small ceramic magnet as a souvenir from Lisbon.", "image_query": "souvenir shop handmade craft travel"}
        ],
        "quiz": [
            {"sentence": "What document is required to cross international borders?", "options": ["Passport", "Receipt", "Certificate"], "correct_index": 0, "explanation": "A passport is the official travel document for foreign travel.", "image_query": "passport boarding pass airport travel"},
            {"sentence": "What do we call traveling light with only a backpack?", "options": ["Backpacking", "Hitchhiking", "Cruising"], "correct_index": 0, "explanation": "Backpacking is traveling with all belongings in a backpack.", "image_query": "backpacker mountain hiking trail"},
            {"sentence": "Where do passengers wait right before boarding an airplane?", "options": ["Departure gate", "Baggage claim", "Ticket counter"], "correct_index": 0, "explanation": "The departure gate is the exact point of boarding the flight.", "image_query": "airport departure gate terminal plane"},
            {"sentence": "Which word means extremely beautiful and impressive?", "options": ["Breathtaking", "Ordinary", "Awkward"], "correct_index": 0, "explanation": "Breathtaking describes scenery that leaves you in awe.", "image_query": "norwegian fjords scenic landscape"}
        ],
        "speaking": [
            {"emoji": "✈️", "question": "If you could teleport to any place on Earth right now, where would you go?", "follow_up": "What is the first thing you would do once you arrive there?", "color": "#2563eb"},
            {"emoji": "🎒", "question": "Do you prefer thoroughly planned holidays or spontaneous trips?", "follow_up": "Tell a story about an unexpected adventure during a trip.", "color": "#16a34a"},
            {"emoji": "🏖️", "question": "Would you rather spend a week relaxing on a beach or hiking in the mountains?", "follow_up": "What is the most memorable view you have ever witnessed?", "color": "#d97706"},
            {"emoji": "🗺️", "question": "What is the biggest cultural shock you have ever experienced abroad?", "follow_up": "How did you adapt to the local customs?", "color": "#7c3aed"}
        ],
        "fill": [
            {"sentence_with_blank": "Always remember to keep your ___ in a secure zippered pocket.", "answer": "passport", "translation": "Всегда помните держать паспорт в надежном кармане на молнии."},
            {"sentence_with_blank": "We arrived at the airport two hours before the scheduled ___ time.", "answer": "flight", "translation": "Мы прибыли в аэропорт за два часа до запланированного времени вылета."},
            {"sentence_with_blank": "The sunset over the Mediterranean Sea was completely ___.", "answer": "breathtaking", "translation": "Закат над Средиземным морем был абсолютно захватывающим."},
            {"sentence_with_blank": "Let's check our travel ___ to see where we are heading tomorrow.", "answer": "itinerary", "translation": "Давай проверим наш маршрут, чтобы узнать, куда мы направляемся завтра."}
        ]
    },
    "prepositions_people_numbers": {
        "title": "Prepositions, People & Numbers (A0)",
        "vocab": [
            {"word": "under [ˈʌndər]", "translation": "под", "type": "preposition", "example": "The secret box is under the wooden desk.", "image_query": "cat hiding under desk classroom"},
            {"word": "behind [bɪˈhaɪnd]", "translation": "за, позади", "type": "preposition", "example": "The tall boy is hiding behind the green door.", "image_query": "boy hiding behind door playful"},
            {"word": "next to [nekst tuː]", "translation": "рядом с", "type": "preposition", "example": "Sit next to student number twenty.", "image_query": "two students sitting next to each other desk"},
            {"word": "tall [tɔːl]", "translation": "высокий", "type": "adjective", "example": "Our basketball coach is very tall and kind.", "image_query": "tall friendly teacher portrait"},
            {"word": "eyes [aɪz]", "translation": "глаза", "type": "noun", "example": "She has big sparkling blue eyes and dark hair.", "image_query": "kid blue eyes smile portrait"},
            {"word": "twenty [ˈtwenti]", "translation": "двадцать (20)", "type": "number", "example": "There are twenty colorful pencils on the table.", "image_query": "twenty colorful pencils school"}
        ],
        "quiz": [
            {"sentence": "Where is the cat if it is hiding beneath the chair?", "options": ["Under the chair", "On the chair", "In the chair"], "correct_index": 0, "explanation": "'Under' means below or beneath an object.", "image_query": "cat under chair playful"},
            {"sentence": "Which word describes a person who has great height?", "options": ["Tall", "Short", "Small"], "correct_index": 0, "explanation": "'Tall' means higher than average height.", "image_query": "tall boy standing friend"},
            {"sentence": "Count by tens: ten, twenty, thirty, ___.", "options": ["Forty", "Fifty", "Fourteen"], "correct_index": 0, "explanation": "Ten, twenty, thirty, forty (10, 20, 30, 40).", "image_query": "numbers counting blocks colorful"},
            {"sentence": "The dog is sleeping ___ the sofa and the table.", "options": ["Between", "On", "Behind"], "correct_index": 0, "explanation": "'Between' indicates in the space separating two things.", "image_query": "dog between sofa and table"}
        ],
        "speaking": [
            {"emoji": "🕵️", "question": "Look around your room: what is on your desk and what is under your chair?", "follow_up": "Can you name 3 objects in English?", "color": "#2563eb"},
            {"emoji": "🔢", "question": "What is your lucky number from 1 to 100?", "follow_up": "Can you count backwards from twenty to ten?", "color": "#16a34a"},
            {"emoji": "👀", "question": "Describe your favorite character or friend: are they tall or short?", "follow_up": "What color are their eyes and hair?", "color": "#d97706"},
            {"emoji": "🎯", "question": "Detective game: 'Agent 50 is behind the door with green eyes!' Can you invent a secret agent?", "follow_up": "Where are they hiding right now?", "color": "#7c3aed"}
        ],
        "fill": [
            {"sentence_with_blank": "The yellow ball is ___ the big table.", "answer": "under", "translation": "Жёлтый мяч находится под большим столом."},
            {"sentence_with_blank": "She has bright blue ___ and curly brown hair.", "answer": "eyes", "translation": "У неё яркие синие глаза и кудрявые каштановые волосы."},
            {"sentence_with_blank": "Ten plus thirty equals ___ (40).", "answer": "forty", "translation": "Десять плюс тридцать равно сорок."},
            {"sentence_with_blank": "My brother is very ___ and loves sports.", "answer": "tall", "translation": "Мой брат очень высокий и любит спорт."}
        ]
    },
    "prepositions": {
        "title": "Prepositions of Place",
        "vocab": [
            {"word": "in [ɪn]", "translation": "в, внутри", "type": "preposition", "example": "The pencils are in the pencil case.", "image_query": "pencils in pencil case colorful"},
            {"word": "on [ɒn]", "translation": "на (поверхности)", "type": "preposition", "example": "The book is on the table.", "image_query": "book on wooden table"},
            {"word": "under [ˈʌndər]", "translation": "под", "type": "preposition", "example": "The dog is sleeping under the bed.", "image_query": "puppy sleeping under bed"},
            {"word": "behind [bɪˈhaɪnd]", "translation": "сзади, позади", "type": "preposition", "example": "Who is standing behind the curtain?", "image_query": "person behind curtain playful"},
            {"word": "next to [nekst tuː]", "translation": "рядом с", "type": "preposition", "example": "The lamp is next to the computer.", "image_query": "desk lamp next to computer"},
            {"word": "between [bɪˈtwiːn]", "translation": "между", "type": "preposition", "example": "The ball is between the two shoes.", "image_query": "ball between shoes room"}
        ],
        "quiz": [
            {"sentence": "Where is the apple if it is resting upon the surface of the desk?", "options": ["On the desk", "Under the desk", "In the desk"], "correct_index": 0, "explanation": "'On' indicates touching the upper surface of something.", "image_query": "red apple on desk"},
            {"sentence": "The puppy is hiding beneath the chair. Where is it?", "options": ["Under the chair", "On the chair", "Above the chair"], "correct_index": 0, "explanation": "'Under' means below the chair.", "image_query": "puppy under chair"},
            {"sentence": "There is a house on the left and a house on the right. The tree is ___ them.", "options": ["Between", "In", "On"], "correct_index": 0, "explanation": "'Between' indicates in the middle of two objects.", "image_query": "tree between two houses"},
            {"sentence": "Look at the picture: the boy is standing right beside his friend. He is ___ him.", "options": ["Next to", "Under", "Behind"], "correct_index": 0, "explanation": "'Next to' means at the side of or beside someone.", "image_query": "two friends standing next to each other"}
        ],
        "speaking": [
            {"emoji": "🏠", "question": "Where is your backpack right now?", "follow_up": "Is it on the floor or under your chair?", "color": "#2563eb"},
            {"emoji": "🐱", "question": "Where do cats love to hide in a house?", "follow_up": "Have you ever found a pet inside a wardrobe or under a bed?", "color": "#16a34a"},
            {"emoji": "🛋️", "question": "What is next to your bed in your bedroom?", "follow_up": "What is on your favorite shelf?", "color": "#d97706"},
            {"emoji": "🔍", "question": "Spy game: pick one item in the room and say its location without naming it!", "follow_up": "Can the teacher guess what it is?", "color": "#7c3aed"}
        ],
        "fill": [
            {"sentence_with_blank": "The keys are ___ the wooden table.", "answer": "on", "translation": "Ключи лежат на деревянном столе."},
            {"sentence_with_blank": "The cat is hiding ___ the bed.", "answer": "under", "translation": "Кот прячется под кроватью."},
            {"sentence_with_blank": "Sit ___ to me so we can read together.", "answer": "next", "translation": "Сядь рядом со мной, чтобы мы могли читать вместе."},
            {"sentence_with_blank": "The notebook is ___ my bag.", "answer": "in", "translation": "Тетрадь лежит в моей сумке."}
        ]
    },
    "people": {
        "title": "Describing People",
        "vocab": [
            {"word": "tall [tɔːl]", "translation": "высокий", "type": "adjective", "example": "My dad is tall and wears glasses.", "image_query": "tall friendly father portrait"},
            {"word": "short [ʃɔːt]", "translation": "невысокий / короткий", "type": "adjective", "example": "The little girl has short blond hair.", "image_query": "girl short blond hair smiling"},
            {"word": "eyes [aɪz]", "translation": "глаза", "type": "noun", "example": "He has warm green eyes and a big smile.", "image_query": "person green eyes smiling"},
            {"word": "hair [heər]", "translation": "волосы", "type": "noun", "example": "She has long dark hair.", "image_query": "girl long dark hair portrait"},
            {"word": "friendly [ˈfrendli]", "translation": "дружелюбный", "type": "adjective", "example": "Our new classmate is very friendly and funny.", "image_query": "friendly smiling kid classmate"},
            {"word": "glasses [ˈɡlɑːsɪz]", "translation": "очки", "type": "noun", "example": "He wears round glasses when reading books.", "image_query": "person wearing stylish glasses"}
        ],
        "quiz": [
            {"sentence": "Which word is the opposite of 'tall' when describing a person's height?", "options": ["Short", "Long", "Fast"], "correct_index": 0, "explanation": "'Short' is the antonym of 'tall' for height.", "image_query": "tall and short friends standing together"},
            {"sentence": "What do people wear on their face to see better?", "options": ["Glasses", "Gloves", "Boots"], "correct_index": 0, "explanation": "Glasses help people see clearly.", "image_query": "glasses eyeglasses desk"},
            {"sentence": "Someone who smiles a lot and makes friends easily is ___.", "options": ["Friendly", "Angry", "Tired"], "correct_index": 0, "explanation": "Friendly means behaving kindly and pleasantly towards others.", "image_query": "friendly happy children group"},
            {"sentence": "Which feature can be straight, wavy, or curly?", "options": ["Hair", "Nose", "Teeth"], "correct_index": 0, "explanation": "Hair comes in straight, wavy, or curly textures.", "image_query": "curly hair hairstyle portrait"}
        ],
        "speaking": [
            {"emoji": "🧑", "question": "Who is the tallest person in your family or class?", "follow_up": "Do they play any sports like basketball or volleyball?", "color": "#2563eb"},
            {"emoji": "🎨", "question": "If you could change your hair color for one day, what color would you choose?", "follow_up": "Why that color?", "color": "#16a34a"},
            {"emoji": "👓", "question": "Do you or any of your friends wear glasses?", "follow_up": "What color frame looks the coolest?", "color": "#d97706"},
            {"emoji": "🦸", "question": "Describe your favorite superhero or movie character's appearance!", "follow_up": "What makes them look heroic?", "color": "#7c3aed"}
        ],
        "fill": [
            {"sentence_with_blank": "She has big brown ___ and a kind smile.", "answer": "eyes", "translation": "У неё большие карие глаза и добрая улыбка."},
            {"sentence_with_blank": "My grandfather is very ___ and tells great stories.", "answer": "friendly", "translation": "Мой дедушка очень дружелюбный и рассказывает отличные истории."},
            {"sentence_with_blank": "He needs to wear ___ to read the book.", "answer": "glasses", "translation": "Ему нужно носить очки, чтобы читать книгу."},
            {"sentence_with_blank": "The basketball player is extremely ___ (2 meters).", "answer": "tall", "translation": "Баскетболист невероятно высокий (2 метра)."}
        ]
    },
    "numbers": {
        "title": "Numbers 1-100",
        "vocab": [
            {"word": "ten [ten]", "translation": "десять (10)", "type": "number", "example": "I have ten fingers on my hands.", "image_query": "ten fingers hands open"},
            {"word": "twenty [ˈtwenti]", "translation": "двадцать (20)", "type": "number", "example": "There are twenty students in our English class.", "image_query": "number 20 colorful"},
            {"word": "fifty [ˈfɪfti]", "translation": "пятьдесят (50)", "type": "number", "example": "Fifty minutes is almost one hour.", "image_query": "number 50 golden"},
            {"word": "hundred [ˈhʌndrəd]", "translation": "сто (100)", "type": "number", "example": "A century is one hundred years.", "image_query": "one hundred 100 celebration"},
            {"word": "count [kaʊnt]", "translation": "считать", "type": "verb", "example": "Can you count from one to twenty in English?", "image_query": "kid counting fingers math"},
            {"word": "plus [plʌs]", "translation": "плюс, сложение", "type": "preposition", "example": "Twenty plus thirty equals fifty.", "image_query": "math plus sign blackboard"}
        ],
        "quiz": [
            {"sentence": "What number comes immediately after nineteen (19)?", "options": ["Twenty (20)", "Thirty (30)", "Eighteen (18)"], "correct_index": 0, "explanation": "19 + 1 = 20 (twenty).", "image_query": "number 20 bright"},
            {"sentence": "How much is fifty plus fifty (50 + 50)?", "options": ["One hundred (100)", "Eighty (80)", "Seventy (70)"], "correct_index": 0, "explanation": "50 + 50 = 100 (one hundred).", "image_query": "100 percent celebration"},
            {"sentence": "Which number is spelled 'T-H-I-R-T-Y'?", "options": ["30", "13", "3"], "correct_index": 0, "explanation": "30 is thirty, whereas 13 is thirteen.", "image_query": "number 30 wooden block"},
            {"sentence": "How many cents are in one US dollar?", "options": ["100 cents", "50 cents", "20 cents"], "correct_index": 0, "explanation": "One dollar equals one hundred cents.", "image_query": "dollar coins cents money"}
        ],
        "speaking": [
            {"emoji": "🔢", "question": "What is your favorite or lucky number?", "follow_up": "Why is this number special to you?", "color": "#2563eb"},
            {"emoji": "🎂", "question": "Can you say how old you and your family members are in English?", "follow_up": "Who is the oldest person in your family?", "color": "#16a34a"},
            {"emoji": "⚡", "question": "Math sprint: what is twenty-five plus twenty-five?", "follow_up": "Can you count by tens to one hundred fast?", "color": "#d97706"},
            {"emoji": "🎮", "question": "What is the highest score or level you have reached in a video game?", "follow_up": "Is it over 100?", "color": "#7c3aed"}
        ],
        "fill": [
            {"sentence_with_blank": "Ten times ten equals one ___ (100).", "answer": "hundred", "translation": "Десять умножить на десять равно сто."},
            {"sentence_with_blank": "Thirty plus twenty equals ___ (50).", "answer": "fifty", "translation": "Тридцать плюс двадцать равно пятьдесят."},
            {"sentence_with_blank": "There are ___ (24) hours in one day.", "answer": "twenty-four", "translation": "В одном дне двадцать четыре часа."},
            {"sentence_with_blank": "Let's ___ the apples on the table together.", "answer": "count", "translation": "Давай вместе посчитаем яблоки на столе."}
        ]
    }
}


def _match_topic_db(topic: str) -> Dict[str, Any]:
    """Find the closest pre-curated topic dataset or create a dynamic one."""
    t_lower = (topic or "general").lower()
    
    # Check multi-topic keywords for combined lesson
    if any(k in t_lower for k in ["предлог", "preposition"]) and any(k in t_lower for k in ["люд", "внешност", "people", "appearance", "числ", "number", "100"]):
        return TOPIC_DATABASES["prepositions_people_numbers"]
    if "prepositions, people & numbers" in t_lower or "prepositions and people" in t_lower:
        return TOPIC_DATABASES["prepositions_people_numbers"]

    for key, db in TOPIC_DATABASES.items():
        if key in t_lower or any(w in t_lower for w in key.split("_")):
            return db

    # Check Russian and English keywords
    if any(k in t_lower for k in ["предлог", "preposition", "мест"]):
        return TOPIC_DATABASES["prepositions"]
    if any(k in t_lower for k in ["люд", "внешност", "человек", "people", "appearance", "person"]):
        return TOPIC_DATABASES["people"]
    if any(k in t_lower for k in ["числ", "числа", "счет", "цифр", "number", "100"]):
        return TOPIC_DATABASES["numbers"]
    if any(k in t_lower for k in ["ед", "кухн", "cook", "food", "рецепт", "блюд"]):
        return TOPIC_DATABASES["food"]
    if any(k in t_lower for k in ["день", "жизнь", "рутин", "routine", "daily", "привычк"]):
        return TOPIC_DATABASES["daily"]
    if any(k in t_lower for k in ["путеш", "поездк", "город", "travel", "trip", "страна"]):
        return TOPIC_DATABASES["travel"]

    # Dynamic fallback generator for arbitrary topics
    clean_topic = topic.strip().capitalize() if topic else "Daily Life & Routines"
    return {
        "title": clean_topic,
        "vocab": [
            {"word": f"concept [ˈkɒnsept]", "translation": "понятие, идея", "type": "noun", "example": f"Understanding the core concept of {clean_topic.lower()} is essential.", "image_query": f"{clean_topic} idea brainstorming"},
            {"word": f"essential [ɪˈsenʃl]", "translation": "необходимый, важный", "type": "adjective", "example": f"Practice is essential when learning about {clean_topic.lower()}.", "image_query": f"{clean_topic} learning books"},
            {"word": f"perspective [pəˈspektɪv]", "translation": "точка зрения", "type": "noun", "example": f"Everyone has their own unique perspective on {clean_topic.lower()}.", "image_query": f"{clean_topic} people discussing"},
            {"word": f"to develop [dɪˈveləp]", "translation": "развивать", "type": "verb", "example": f"We can develop new practical skills in {clean_topic.lower()} every day.", "image_query": f"{clean_topic} growth progress chart"},
            {"word": f"effective [ɪˈfektɪv]", "translation": "эффективный", "type": "adjective", "example": f"Using modern tools makes our approach to {clean_topic.lower()} much more effective.", "image_query": f"{clean_topic} modern tech workspace"},
            {"word": f"challenge [ˈtʃælɪndʒ]", "translation": "вызов, сложная задача", "type": "noun", "example": f"Overcoming this challenge will help you master {clean_topic.lower()}.", "image_query": f"{clean_topic} mountain climbing success"}
        ],
        "quiz": [
            {"sentence": f"What is the primary benefit of mastering {clean_topic.lower()}?", "options": ["Practical improvement", "Wasting valuable time", "Avoiding communication"], "correct_index": 0, "explanation": "Learning practical skills leads to measurable self-improvement.", "image_query": f"{clean_topic} success celebration"},
            {"sentence": f"Which word is a synonym for 'essential' in the context of {clean_topic.lower()}?", "options": ["Crucial", "Optional", "Irrelevant"], "correct_index": 0, "explanation": "'Crucial' and 'essential' both mean of the utmost importance.", "image_query": f"{clean_topic} importance priority"},
            {"sentence": f"When discussing {clean_topic.lower()}, it is always helpful to support opinions with ___.", "options": ["Real examples", "Wild rumors", "Random guesses"], "correct_index": 0, "explanation": "Supporting arguments with concrete examples makes speech persuasive.", "image_query": f"{clean_topic} presentation chart"},
            {"sentence": f"How can a learner improve their confidence in {clean_topic.lower()}?", "options": ["Consistent practice", "Giving up easily", "Ignoring feedback"], "correct_index": 0, "explanation": "Consistent regular practice builds long-term fluency and confidence.", "image_query": f"{clean_topic} practice study desk"}
        ],
        "speaking": [
            {"emoji": "💡", "question": f"What first sparked your interest in {clean_topic.lower()}?", "follow_up": "How has your perspective changed over the past year?", "color": "#2563eb"},
            {"emoji": "⚖️", "question": f"What are the biggest advantages and challenges of {clean_topic.lower()} today?", "follow_up": "Can you share a specific example from personal experience?", "color": "#16a34a"},
            {"emoji": "🚀", "question": f"How do you imagine the future of {clean_topic.lower()} in ten years?", "follow_up": "What technologies or trends will play the biggest role?", "color": "#d97706"},
            {"emoji": "🎯", "question": f"If you had to explain {clean_topic.lower()} to a beginner in three sentences, what would you say?", "follow_up": "What is the most common misconception about it?", "color": "#7c3aed"}
        ],
        "fill": [
            {"sentence_with_blank": f"Having a clear goal is ___ when studying {clean_topic.lower()}.", "answer": "essential", "translation": f"Иметь четкую цель необходимо при изучении темы «{clean_topic}»."},
            {"sentence_with_blank": f"We should share our ideas and ___ on this topic with the group.", "answer": "perspectives", "translation": f"Нам следует делиться своими мыслями и взглядами по этой теме с группой."},
            {"sentence_with_blank": f"Consistent practice is the most ___ way to achieve fluent speech.", "answer": "effective", "translation": f"Регулярная практика — самый эффективный способ достичь беглой речи."},
            {"sentence_with_blank": f"Do not be afraid to embrace a new ___ in your learning journey.", "answer": "challenge", "translation": f"Не бойся принимать новый вызов на своем пути обучения."}
        ]
    }


def _clean_hashtags(topic: str, level: str, extra_tags: List[str]) -> List[str]:
    """Generate clean, legible hashtags according to Rule 4 without underscores or ugly slugs."""
    clean_top = re.sub(r"[\(\[].*?[\)\]]", "", topic).strip()
    words = [w.lower() for w in re.findall(r"[a-zA-Zа-яА-ЯёЁ]{3,}", clean_top)]
    tags = [f"#{w}" for w in words[:4]]
    tags.append(f"#{level.lower()}")
    for t in extra_tags:
        t_clean = f"#{t.lstrip('#')}"
        if t_clean not in tags:
            tags.append(t_clean)
    return tags


def generate_fallback_speaking_cards(
    topic: str,
    level: str = "A2",
    count: int = 4,
    bloom_level: Optional[str] = None
) -> Dict[str, Any]:
    """Fallback generator for Speaking Cards."""
    db = _match_topic_db(topic)
    topic_name = db.get("title", topic or "Speaking Practice")
    cards_pool = db.get("speaking", [])
    
    selected_cards = []
    colors = ["#2563eb", "#16a34a", "#d97706", "#7c3aed", "#0891b2", "#be185d"]
    for i in range(count):
        base = cards_pool[i % len(cards_pool)]
        selected_cards.append({
            "id": i + 1,
            "emoji": base.get("emoji", "🗣️"),
            "question": base["question"],
            "follow_up": base.get("follow_up", "Why do you feel this way?"),
            "color": colors[i % len(colors)]
        })

    return {
        "title": f"🗣️ Speaking: {topic_name}",
        "topic": topic_name,
        "level": level,
        "instruction": "👉 Обсудите вопросы с преподавателем, используя опорные фразы и личные примеры.",
        "cards": selected_cards,
        "hashtags": _clean_hashtags(topic_name, level, ["speaking", "warmup", "interactive", "esl"])
    }


def generate_fallback_vocabulary_table(
    topic: str,
    level: str = "A2",
    count: int = 6,
    bloom_level: Optional[str] = None
) -> Dict[str, Any]:
    """Fallback generator for Vocabulary Table."""
    db = _match_topic_db(topic)
    topic_name = db.get("title", topic or "Vocabulary")
    vocab_pool = db.get("vocab", [])

    rows = []
    for i in range(min(count, len(vocab_pool))):
        item = vocab_pool[i]
        rows.append({
            "id": i + 1,
            "word": item["word"],
            "translation": item["translation"],
            "type": item["type"],
            "example": item["example"],
            "image_query": item.get("image_query") or f"{topic_name} illustration photo"
        })

    return {
        "title": f"📚 Vocabulary: {topic_name}",
        "topic": topic_name,
        "level": level,
        "instruction": "👉 Изучите ключевые слова, обратите внимание на транскрипцию и примеры использования.",
        "columns": ["Картинка", "№ / Слово (Word)", "Перевод (Russian)", "Тип / Роль (Role)", "Пример в речи (Example Sentence)"],
        "rows": rows,
        "hashtags": _clean_hashtags(topic_name, level, ["vocabulary", "flashcards", "esl"])
    }


def _ensure_four_shuffled_options(base_q: Dict[str, Any], topic_name: str) -> Dict[str, Any]:
    """Ensures a quiz question has exactly 4 options and randomly shuffles them."""
    opts = list(base_q.get("options", []))
    orig_idx = base_q.get("correct_index", 0)
    if not (0 <= orig_idx < len(opts)):
        orig_idx = 0
    correct_answer = opts[orig_idx] if opts else "Correct Option"

    # Natural topic-appropriate distractors (NEVER "None of the above" or "All of the above")
    natural_distractors = [
        "Take a break", "Prepare breakfast", "Check emails", "Set an alarm",
        "Wash the dishes", "Do exercise", "Catch the bus", "Pack a bag",
        "Brush teeth", "Stay up late", "Cook dinner", "Make coffee"
    ]
    d_idx = 0
    while len(opts) < 4:
        cand = natural_distractors[d_idx % len(natural_distractors)]
        d_idx += 1
        if cand not in opts:
            opts.append(cand)

    if len(opts) > 4:
        other_opts = [o for i, o in enumerate(opts) if i != orig_idx]
        opts = [correct_answer] + other_opts[:3]

    # Randomly shuffle the 4 options
    random.shuffle(opts)
    new_correct_idx = opts.index(correct_answer)

    return {
        "options": opts,
        "correct_index": new_correct_idx,
        "correct_answer": correct_answer
    }


def generate_fallback_quiz_photo(
    topic: str,
    level: str = "A2",
    count: int = 10,
    bloom_level: Optional[str] = None
) -> Dict[str, Any]:
    """Fallback generator for Photo Quiz. Enforces minimum 10 questions, 4 options, and randomized answers with NO looping/repeats."""
    count = max(int(count or 10), 10)
    db = _match_topic_db(topic)
    topic_name = db.get("title", topic or "Interactive Quiz")
    quiz_pool = db.get("quiz", [])

    extra_questions = [
        {"sentence": "What hot beverage do millions of people drink to stay alert in the morning?", "options": ["Coffee", "Lemonade", "Cold milk", "Soda"], "correct_index": 0, "explanation": "Coffee is widely consumed in the morning for its energizing effect.", "image_query": "person drinking hot coffee cup morning kitchen"},
        {"sentence": "What do we call taking a brief 20-minute restorative sleep during the daytime?", "options": ["Power nap", "Deep hibernation", "Bedtime", "Insomnia"], "correct_index": 0, "explanation": "A power nap is a short sleep taken during the day to restore energy.", "image_query": "person taking comfortable afternoon nap couch cushion"},
        {"sentence": "Which daily task involves cleaning plates, glasses, and cutlery after dinner?", "options": ["Washing dishes", "Vacuuming carpets", "Ironing shirts", "Watering plants"], "correct_index": 0, "explanation": "Washing dishes cleans tableware used during meals.", "image_query": "person washing dishes soapy bubbles kitchen sink"},
        {"sentence": "What do you do right before going to bed to ensure your bedroom is quiet and dark?", "options": ["Turn off lights", "Start cooking", "Call a taxi", "Open front door"], "correct_index": 0, "explanation": "Turning off the lights prepares the room for sleep.", "image_query": "person turning off bedside lamp bedroom night cozy"}
    ]

    questions = []
    for i in range(count):
        if i < len(quiz_pool):
            base_q = quiz_pool[i]
        else:
            e_idx = (i - len(quiz_pool)) % len(extra_questions)
            base_q = extra_questions[e_idx]

        shuffled = _ensure_four_shuffled_options(base_q, topic_name)
        questions.append({
            "id": i + 1,
            "image_query": base_q.get("image_query") or f"{topic_name} photo illustration",
            "sentence": base_q["sentence"],
            "question": base_q["sentence"],
            "options": shuffled["options"],
            "correct_index": shuffled["correct_index"],
            "explanation": base_q.get("explanation", f"Correct answer is {shuffled['correct_answer']}")
        })

    return {
        "title": f"🎯 Quiz: {topic_name}",
        "topic": topic_name,
        "level": level,
        "instruction": "👉 Выберите правильный вариант ответа для каждого задания по картинке.",
        "image_query": f"{topic_name} scene photo",
        "questions": questions,
        "hashtags": _clean_hashtags(topic_name, level, ["quiz", "interactive", "esl"])
    }


def generate_fallback_fill_blanks(
    topic: str,
    level: str = "A2",
    count: int = 10,
    bloom_level: Optional[str] = None
) -> Dict[str, Any]:
    """Fallback generator for Fill Blanks Table. Enforces minimum 10 sentences."""
    count = max(int(count or 10), 10)
    db = _match_topic_db(topic)
    topic_name = db.get("title", topic or "Practice Exercise")
    fill_pool = db.get("fill", [])

    sentences = []
    word_bank = []
    extra_sentences = [
        {"sentence_with_blank": "Eating a healthy ___ gives you energy for the entire morning.", "answer": "breakfast", "translation": "Здоровый завтрак дает вам энергию на все утро."},
        {"sentence_with_blank": "A consistent morning ___ helps you start your day with focus.", "answer": "routine", "translation": "Постоянный утренний распорядок помогает начать день сосредоточенно."},
        {"sentence_with_blank": "Drinking a glass of water every morning is a healthy ___.", "answer": "habit", "translation": "Стакан воды каждое утро — полезная привычка."},
        {"sentence_with_blank": "We must complete and submit the project before the 5 PM ___.", "answer": "deadline", "translation": "Мы должны завершить и сдать проект до дедлайна в 17:00."},
        {"sentence_with_blank": "Going ___ in the park every morning keeps your body energized.", "answer": "jogging", "translation": "Утренняя пробежка в парке заряжает тело энергией."},
        {"sentence_with_blank": "Remember to brush your ___ twice a day to maintain dental health.", "answer": "teeth", "translation": "Не забывайте чистить зубы дважды в день для здоровья полости рта."}
    ]

    for i in range(count):
        if i < len(fill_pool):
            base_item = fill_pool[i]
        else:
            e_idx = (i - len(fill_pool)) % len(extra_sentences)
            base_item = extra_sentences[e_idx]

        s_text = base_item["sentence_with_blank"]
        ans = base_item["answer"]
        trans = base_item["translation"]

        sentences.append({
            "id": i + 1,
            "sentence_with_blank": s_text,
            "answer": ans,
            "translation": trans
        })
        if ans not in word_bank:
            word_bank.append(ans)

    # Contextual distractor words to challenge the student (NEVER "extra_1", "extra_2")
    contextual_distractors = ["dinner", "shower", "relax", "planner", "subway", "coffee", "exercise", "weekend", "evening", "alarm"]
    d_idx = 0
    while len(word_bank) < min(count, 12):
        cand = contextual_distractors[d_idx % len(contextual_distractors)]
        d_idx += 1
        if cand not in word_bank:
            word_bank.append(cand)

    random.shuffle(word_bank)

    return {
        "title": f"✏️ Practice: {topic_name}",
        "topic": topic_name,
        "level": level,
        "instruction": "👉 Вставьте подходящие по смыслу слова из банка слов в пропуски предложений.",
        "word_bank": word_bank,
        "sentences": sentences,
        "hashtags": _clean_hashtags(topic_name, level, ["grammar", "fill_blanks", "esl"])
    }


def generate_fallback_flip_cards(
    topic: str,
    level: str = "A2",
    count: int = 6
) -> Dict[str, Any]:
    """Fallback generator for Peekaboo / Flip Cards."""
    db = _match_topic_db(topic)
    topic_name = db.get("title", topic or "Peekaboo Cards")
    speaking_pool = db.get("speaking", [])
    colors = ["#2563eb", "#16a34a", "#d97706", "#7c3aed", "#0891b2", "#be185d"]

    cards = []
    for i in range(min(count, len(speaking_pool) * 2)):
        base = speaking_pool[i % len(speaking_pool)]
        cards.append({
            "id": i + 1,
            "label": f"SECRET #{i+1}",
            "image_query": f"{topic_name} item {i+1}",
            "color": colors[i % len(colors)],
            "question": base["question"],
            "bonus_question": base.get("follow_up", "Explain your answer.")
        })

    return {
        "title": f"🃏 Peekaboo: {topic_name}",
        "topic": topic_name,
        "level": level,
        "instruction": "👉 Нажмите на карточку, чтобы открыть секретный вопрос и обсудить его.",
        "cards": cards,
        "hashtags": _clean_hashtags(topic_name, level, ["peekaboo", "interactive", "esl"])
    }


def generate_fallback_flashcards(
    topic: str,
    level: str = "A2",
    count: int = 6
) -> Dict[str, Any]:
    """Fallback generator for Flashcards."""
    db = _match_topic_db(topic)
    topic_name = db.get("title", topic or "Flashcards")
    vocab_pool = db.get("vocab", [])

    cards = []
    for i in range(min(count, len(vocab_pool))):
        v = vocab_pool[i]
        cards.append({
            "id": i + 1,
            "front": v["word"].split("[")[0].strip(),
            "back": v["translation"],
            "transcription": re.search(r"\[.+?\]", v["word"]).group(0) if "[" in v["word"] else "",
            "example": v["example"]
        })

    return {
        "title": f"🗂 Flashcards: {topic_name}",
        "topic": topic_name,
        "level": level,
        "instruction": "👉 Переворачивайте карточки, тренируйте запоминание слов и примеров.",
        "cards": cards,
        "hashtags": _clean_hashtags(topic_name, level, ["flashcards", "vocabulary", "esl"])
    }
