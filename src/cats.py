import re
# Bulgarian stems + English; first match in this order wins (specific before generic)
CATS=[
('nuc','Nuclear & strategic',r'ядрен|ядро|nuclear|балистичн|ICBM|хиперзвук|hypersonic|Орешник|Сармат|стратегическ\w+ бомбард|уран'),
('air','Air defence & missiles',r'ПВО|ПРО\b|Patriot|Пейтриът|С-300|С-400|С-500|прехва|противоракет|air defen|интерцепт|Железен купол|Iron Dome|THAAD|Arrow'),
('cyb','Cyber & information',r'кибер|хакер|cyber|hack|дезинформ|пропаганд|фалшиви новини|Starlink|интернет блок'),
('ter','Terror & hostages',r'терор|заложни|атентат|самоубийствен|terror|hostage|похити|отвлеч'),
('pro','Protests & unrest',r'протест|демонстрац|бунт|безредици|размирици|митинг|стачк|протестиращи|переврат|преврат|coup'),
('dis','Disasters & accidents',r'земетресение|наводнен|пожар|катастроф|крушение|взрив в|свлачище|ураган|циклон|цунами|вулкан|earthquake|crash|разби се|падна самолет'),
('arm','Arms & equipment',r'доставк\w+ на оръжи|оръжейн|танкове|Abrams|Leopard|F-16|F-35|Су-57|Су-35|изтребител|HIMARS|ATACMS|Taurus|Storm Shadow|контракт за|продажба на оръжие|боеприпас|снаряди|дронов[ея]\b.*производств'),
('sea','Maritime & shipping',r'кораб|танкер|флот|подводниц|пристанищ|мореплав|Червено море|Ормузк|Босфор|морск|ship|vessel|tanker|navy|fleet|submarine'),
('eng','Energy & economy',r'петрол|газ\b|газов|природен газ|нефт|рафинер|тръбопровод|енерг|санкци|цена на|икономик|бюджет|инфлац|мито|търговск|валут|рубл|долар|oil|gas\b|sanction|tariff|economy|OPEC|ОПЕК|електро'),
('hum','Humanitarian & health',r'бежанц|хуманитар|глад|болест|чума|вирус|епидем|пандем|заразя|COVID|коронавирус|лекар|болниц|жертви сред цивилни|civilian|refugee|humanitarian|vaccine|ваксин'),
('mil','Military move',r'настъпле|офанзив|контраофанзив|пробив|превзе|завзе|освобод|окупир|отстъпл|мобилизац|учени[ея]|маневри|разполож|разгърн|военна база|военни учения|deploy|offensive|exercise|troops|войски|бригад|батальон|полк\b|дивизи|фронт'),
('war','Strike or attack',r'удар|обстрел|атак|бомбард|дрон|ракет|взрив|загин|убит|ранен|нападени|въздушен удар|стрелб|strike|attack|shell|bomb|missile|drone|killed|casualt|десант|САЩ нанес|нанесе'),
('sec','Security & intelligence',r'шпионаж|разузнаван|арест|задържа|ФСБ|ЦРУ|CIA|Мосад|Mossad|МИ6|MI6|ГРУ|контраразузнаван|спецслужб|sabotage|саботаж|espionage|spy|заподозр|обвинен|съд\b|осъден|присъда'),
('dip','Diplomacy & politics',r'преговор|споразумение|среща|президент|премиер|министър|посланик|санкции срещу|дипломат|парламент|избори|правителство|коалиц|закон|гласува|ООН|НАТО|ЕС\b|Европейски съюз|summit|talks|treaty|election|minister|parliament|president|ambassador|cabinet|заяви|коментира|изявление'),
]
RX=[(k,n,re.compile(p,re.I)) for k,n,p in CATS]
def classify(t):
    for k,n,r in RX:
        if r.search(t):return k
    return None
