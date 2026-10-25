import re,geonamescache,pycountry
gc=geonamescache.GeonamesCache();CO=gc.get_countries();CI=gc.get_cities()
big={}
for c in CI.values():
    k=c['countrycode']
    if k not in big or c['population']>big[k]['population']:big[k]=c
PT={}
for iso,c in CO.items():
    cap=[x for x in CI.values() if x['countrycode']==iso and x['name']==c['capital']]
    s=cap[0] if cap else big.get(iso)
    if s:PT[iso]=(s['latitude'],s['longitude'])
PT.update({'UA':(49.0,32.0),'RU':(56.0,40.0),'SY':(35.0,38.5),'IR':(32.4,53.7),'PS':(31.45,34.4),'IL':(31.5,34.9),'IQ':(33.0,43.7),'SA':(24.0,45.0),'CN':(34.5,104.0),'US':(38.9,-77.04),'IN':(22.0,79.0),'KZ':(48.0,67.0),'YE':(15.5,47.5),'LB':(33.85,35.85),'SD':(15.5,30.0),'ML':(17.5,-2.0),'ET':(9.0,39.5),'CD':(-3.0,23.5),'LY':(27.0,17.0),'NE':(17.0,9.0),'BY':(53.7,27.9),'TR':(39.0,35.0),'EU':(50.85,4.35),'UN':(40.75,-73.97)})
ISO3={}  # iso2 -> numeric id string
for c in pycountry.countries:ISO3[c.alpha_2]='%03d'%int(c.numeric)
ME={'IL','PS','LB','SY','IR','IQ','YE','SA','AE','QA','KW','BH','OM','JO','TR','EG'}
def theme(iso):
    if iso in('UA','RU','BY','MD'):return 'ua'
    if iso in ME:return 'me'
    if iso in('EU','UN',None):return 'gl'
    c=CO.get(iso,{}).get('continentcode')
    return {'EU':'eu','AF':'af','NA':'am','SA':'am','AS':'as','OC':'as'}.get(c,'gl')
LOW={'US','EU','UN','GB','DE','FR'}
CRX=[(i,re.compile(p,re.I)) for i,p in [
('UA',r'украйн|украин|зеленск|\bВСУ\b'),('RU',r'русия|руск|путин|кремъл|лавров|шойгу'),('IR',r'иран|хаменей|ИРГК|КСИР'),('IL',r'израел|нетаняху|ЦАХАЛ|\bIDF\b'),
('SY',r'сирия|сирийск|асад'),('LB',r'ливан|хизбула|хезболла'),('PS',r'палестин|(?-i:\bГаза\b)|ивицата|хамас|западния бряг'),('IQ',r'ирак|иракск|кюрдистан'),
('SA',r'саудитск|саудитска арабия'),('YE',r'йемен|хути'),('TR',r'турци|ердоган|турск'),('CN',r'китай|китайск|дзинпин'),('TW',r'тайван'),
('KP',r'севернокорей|северна корея|КНДР|ким чен'),('KR',r'южна корея|южнокорей'),('JP',r'япони'),('IN',r'индия|индийск|(?-i:\bМоди\b)'),('PK',r'пакистан'),
('AF',r'афганистан|талибан'),('BY',r'беларус|лукашенко'),('PL',r'полша|полск'),('DE',r'германи|германск'),('FR',r'франци|френск|макрон'),
('GB',r'великобритани|британск'),('BG',r'българи|български'),('RO',r'румъни'),('MD',r'молдов|приднестров'),('GE',r'грузи'),('AM',r'армени'),('AZ',r'азербайджан'),
('VE',r'венецуел|мадуро'),('US',r'съединените щати|\bСАЩ\b|американск|тръмп|байдън|пентагон|вашингтон|белия дом'),('EG',r'египет'),('JO',r'йордани'),('QA',r'катар'),
('AE',r'емирства|\bОАЕ\b'),('KW',r'кувейт'),('BH',r'бахрейн'),('OM',r'(?-i:\bОман\b)'),('SD',r'судан'),('ET',r'етиопи'),('ML',r'(?-i:\bМали\b)'),('NE',r'нигер(?!ийск|ия)'),('NG',r'нигерия|нигерийск'),
('SO',r'сомали'),('LY',r'либия|либий'),('CD',r'конго'),('KZ',r'казахстан'),('RS',r'сърби'),('GR',r'гърци'),('IT',r'итали'),('ES',r'испани'),('NL',r'нидерланд'),
('SE',r'швеци'),('FI',r'финланд'),('NO',r'норвег'),('DK',r'дания'),('LT',r'литва'),('LV',r'латви'),('EE',r'естони'),('CZ',r'чехи'),('SK',r'словаки'),('HU',r'унгари'),
('CA',r'канад'),('MX',r'мексик'),('AU',r'австрали'),('TH',r'тайланд'),('MM',r'мианма|бирма'),('EU',r'европейски съюз|(?-i:\bЕС\b)'),('UN',r'(?-i:\bООН\b)')]]
def C(lat,lon,iso,*ps):return (re.compile('|'.join(ps),re.I),lat,lon,iso)
CITY=[C(50.45,30.52,'UA','киев','киевск'),C(49.99,36.23,'UA','харков'),C(48.59,38.0,'UA','бахмут','артьомовск'),C(47.1,37.55,'UA','мариупол'),C(46.64,32.62,'UA','херсон'),
C(46.48,30.73,'UA','одес'),C(47.84,35.14,'UA','запорож'),C(48.0,37.8,'UA','донецк'),C(48.3,38.2,'UA','донбас'),C(48.57,39.31,'UA','луганск'),
C(45.3,34.4,'UA',r'крим\b','кримск','севастопол','керченск','симферопол'),C(48.46,35.05,'UA','днепър','днепропетровск'),C(49.84,24.03,'UA','лвов'),C(46.97,32.0,'UA','николаев'),
C(50.9,34.8,'UA',r'сумск\w+ област',r'\bСуми\b'),C(51.5,31.3,'UA','чернигов'),C(49.59,34.55,'UA','полтав'),C(47.91,33.39,'UA','кривой рог','кривий рог'),
C(48.14,37.75,'UA','авдеевк'),C(49.7,37.6,'UA','купянск'),C(48.28,37.18,'UA','покровск'),C(48.6,37.8,'UA','часов яр'),C(47.78,37.25,'UA','угледар','вугледар'),
C(48.72,37.55,'UA','краматорск'),C(48.9,24.7,'UA','ивано-франковск'),C(51.27,30.22,'UA','чернобил'),C(47.63,35.4,'UA','запорожка аец','запорожката'),
C(51.73,36.19,'RU','курск'),C(50.6,36.6,'RU','белгород'),C(53.25,34.37,'RU','брянск'),C(51.67,39.2,'RU','воронеж'),C(47.23,39.72,'RU','ростов'),C(45.04,38.98,'RU','краснодар'),
C(44.72,37.77,'RU','новоросийск'),C(59.93,30.34,'RU','петербург'),C(55.76,37.62,'RU','москва','московск'),C(55.79,49.12,'RU','татарстан'),C(56.84,60.6,'RU','екатеринбург'),
C(43.32,45.69,'RU','чечня','грозни'),C(54.7,20.5,'RU','калининград'),C(68.97,33.08,'RU','мурманск'),C(52.29,104.3,'RU','иркутск'),
C(31.45,34.4,'PS','(?-i:\\bГаза\\b)','ивицата'),C(31.29,34.25,'PS','рафах'),C(31.35,34.3,'PS','хан юнис'),C(32.0,35.25,'PS','западния бряг','рамала','дженин','наблус','хеврон'),
C(31.78,35.22,'IL','йерусалим'),C(32.08,34.78,'IL','тел авив','тел-авив'),C(32.8,34.99,'IL','хайфа'),C(33.89,35.5,'LB','бейрут'),C(33.3,35.4,'LB','южен ливан'),
C(33.51,36.29,'SY','дамаск'),C(36.2,37.16,'SY','алепо'),C(35.93,36.63,'SY','идлиб'),C(34.73,36.72,'SY','хомс'),C(35.33,40.14,'SY','дейр ез','дейр-ез'),C(35.95,39.01,'SY','ракка'),
C(33.0,35.8,'SY','голан'),C(35.69,51.39,'IR','техеран'),C(32.65,51.67,'IR','исфахан'),C(28.92,50.84,'IR','бушер'),C(26.57,56.25,'IR','ормуз'),C(27.0,51.5,None,'персийския залив','персийски залив'),
C(33.31,44.36,'IQ','багдад'),C(36.19,44.01,'IQ','ербил'),C(36.34,43.13,'IQ','мосул'),C(15.35,44.21,'YE','(?-i:\\bСана\\b)'),C(14.8,42.95,'YE','ходейда','ходайда'),C(12.8,45.0,'YE',r'\bАден\b'),
C(20.0,38.5,None,'червено море','баб ел'),C(24.71,46.68,'SA','рияд'),C(25.2,55.27,'AE','дубай','абу даби'),C(25.29,51.53,'QA','доха'),C(30.04,31.24,'EG','кайро'),
C(39.93,32.86,'TR','анкара'),C(41.01,28.98,'TR','истанбул'),C(39.9,116.4,'CN','пекин'),C(22.3,114.17,'CN','хонконг','хонг конг'),C(25.03,121.56,'TW','тайпе'),
C(14.0,114.0,None,'южнокитайско','южно китайско'),C(35.68,139.7,'JP','токио'),C(37.57,126.98,'KR','сеул'),C(39.04,125.76,'KP','пхенян'),C(28.6,77.2,'IN','делхи'),C(34.0,76.0,'IN','кашмир'),
C(33.7,73.0,'PK','исламабад'),C(34.53,69.17,'AF','кабул'),C(53.9,27.57,'BY','минск'),C(52.23,21.01,'PL','варшава'),C(50.85,4.35,'EU','брюксел'),C(51.51,-0.13,'GB','лондон'),
C(48.86,2.35,'FR','париж'),C(52.52,13.4,'DE','берлин'),C(38.9,-77.04,'US','вашингтон','пентагон','белия дом'),C(40.75,-73.97,'US','ню йорк'),C(10.5,-66.9,'VE','каракас'),
C(15.5,32.56,'SD','хартум'),C(13.0,25.0,'SD','дарфур'),C(13.5,39.0,'ET','тигре'),C(32.9,13.18,'LY','триполи'),C(40.4,49.87,'AZ','баку'),C(39.8,46.8,'AZ','карабах'),
C(47.0,28.86,'MD','кишинев'),C(44.43,26.1,'RO','букурещ'),C(42.7,23.32,'BG','софия'),C(51.17,71.43,'KZ','астана','нур-султан'),
C(53.2,50.15,'RU','самар','толят','толиати','тольяти'),C(51.53,46.03,'RU','саратов'),C(48.7,44.5,'RU','волгоград'),C(54.73,55.97,'RU','башкортостан','уфа\\b'),
C(58.0,56.25,'RU','пермск','перм\\b'),C(51.77,55.1,'RU','оренбург'),C(56.33,44.0,'RU','нижни новгород','нижегородск'),C(54.63,39.74,'RU','рязан'),
C(54.2,37.6,'RU','тула\\b','тулск'),C(52.6,39.6,'RU','липецк'),C(52.97,36.07,'RU','орловск'),C(54.78,32.05,'RU','смоленск'),
C(57.63,39.87,'RU','ярослав'),C(45.0,41.9,'RU','ставропол'),C(46.35,48.04,'RU','астрахан'),C(59.9,30.3,'RU','ленинградск'),
C(57.8,28.35,'RU','псковск'),C(56.86,35.9,'RU','твер\\b','тверск'),C(54.5,36.25,'RU','калуга','калужк'),C(52.7,41.4,'RU','тамбов'),C(53.2,45.0,'RU','пенза','пензенск'),
C(54.3,48.4,'RU','ульяновск'),C(56.85,53.2,'RU','удмурт'),C(53.4,59.0,'RU','магнитогорск','челябинск')]
FL=re.compile('[\U0001F1E6-\U0001F1FF]{2}')
def flag(f):return ''.join(chr(ord(c)-0x1F1E6+65) for c in f)
def locate(t):
    head=t[:380];best=None
    for rx,la,lo,iso in CITY:
        m=rx.search(head)
        if m and (best is None or m.start()<best[0]):best=(m.start(),la,lo,iso)
    if best:return best[1],best[2],best[3],'p'
    c=[];pos={}
    for f in FL.findall(t[:300]):
        k=flag(f)
        if k in PT or k in('EU','UN'):pos.setdefault(k,len(pos)-1000)
    for iso,rx in CRX:
        m=rx.search(t[:300])
        if m:pos.setdefault(iso,m.start())
    if not pos:
        for iso,rx in CRX:
            m=rx.search(t)
            if m:pos.setdefault(iso,m.start()+500)
    if not pos:return None
    ks=sorted(pos,key=pos.get);dem=set(LOW)
    if 'UA' in ks:dem|={'RU','BY'}
    if set(ks)&{'LB','PS','SY','IQ','YE','IR'}:dem.add('IL')
    if 'TW' in ks:dem|={'CN'}
    if 'SA' in ks and 'YE' in ks:dem.add('SA')
    good=[k for k in ks if k not in dem]
    k=(good or ks)[0]
    if k not in PT:return None
    return PT[k][0],PT[k][1],k,('a' if good else 's')

PHYS=re.compile(r'атакува|атаки|атака|нападн|нападен|напада|удар|обстрел|бомбард|порази|нанес|унищож|нахлу|стрелб|потопи|свали|сваля|взриви|ликвидира|елиминира|разруши|завзе|превзе',re.I)
VERB=re.compile(r'заплаш|обвин|осъд|санкци|експулс|изгон|ултиматум|предупреди|критикува',re.I)
NOUNV=re.compile(r'удар|атак|обстрел|нападен|нахлуван|бомбардиров',re.I)
def mentions(h):
    out=[]
    for iso,rx in CRX:
        for m in rx.finditer(h):out.append((m.start(),m.end(),iso,None))
    for rx,la,lo,iso in CITY:
        if iso:
            for m in rx.finditer(h):out.append((m.start(),m.end(),iso,(la,lo)))
    out.sort(key=lambda x:(x[0],x[1]));return out
def detect(t,loc):
    h=t[:320];m=PHYS.search(h);kind='p'
    if not m:m=VERB.search(h);kind='v'
    if not m:return None
    vp,ve=m.start(),m.end();M=mentions(h)
    before=[x for x in M if x[1]<=vp and vp-x[1]<=70 and x[2]!='UN']
    after=[x for x in M if x[0]>=ve and x[0]-ve<=110]
    att=before[-1] if before else None
    if att is None:
        for x in after:
            pre=h[max(0,x[0]-5):x[0]].lower().rstrip()
            if pre.endswith('от') or (NOUNV.search(m.group()) and pre.endswith('на')):att=x;after=[y for y in after if y is not x];break
    if att is None:return None
    tgt=next((x for x in after if x[2]!=att[2] and x[2]!='UN'),None)
    if tgt is None and loc and loc!=att[2]:tgt=(0,0,loc,None)
    if tgt is None or att[2] not in PT or tgt[2] not in PT:return None
    return att[2],tgt,kind

BND='(?<![А-Яа-яA-Za-z])(?:'
CRX=[(i,re.compile(BND+rx.pattern+')',rx.flags)) for i,rx in CRX]
CITY=[(re.compile(BND+rx.pattern+')',rx.flags),la,lo,iso) for rx,la,lo,iso in CITY]
_d=detect
DELIV=re.compile(r'достав|предостав|военна помощ|пакет с помощ|ще получи|получава|договор за|подпис',re.I);STRONG=re.compile(r'удар по|атака срещу|обстрел|нападение срещу|нанесе|порази',re.I)
def detect(t,loc):
    h=t[:320]
    if DELIV.search(h[:200]) and not STRONG.search(h):return None
    return _d(t,loc)

PASS=re.compile(r'^(?:ударен|поразен|атакуван|обстрелян|нападнат|бомбардиран|унищожен|завзет|превзет|потопен|свален|взривен|разрушен|ликвидиран|елиминиран)(?:а|и|о)?$',re.I)
def _d2(t,loc):
    h=t[:320];m=first_verb(h);kind='p'
    if not m:m=VERB.search(h);kind='v'
    if not m:return None
    vp,ve=m.start(),m.end();M=mentions(h)
    wm=re.match(r'[А-Яа-я]+',h[vp:]);word=wm.group() if wm else ''
    ctry=lambda x:x[3] is None
    after=[x for x in M if x[0]>=ve and x[0]-ve<=110]
    pre=lambda x:h[max(0,x[0]-6):x[0]].lower().rstrip()
    if PASS.match(word):
        att=next((x for x in after if ctry(x) and re.search(r'(?:от|при|чрез|след)$',pre(x))),None)
        tg=[x for x in M if x[1]<=vp and vp-x[1]<=70];tgt=tg[-1] if tg else None
        if tgt is None and loc:tgt=(0,0,loc,None)
        if att is None or tgt is None:return None
    else:
        before=[x for x in M if ctry(x) and x[1]<=vp and vp-x[1]<=70 and x[2]!='UN'];att=before[-1] if before else None;rest=after
        if att is None:
            att=next((x for x in after if ctry(x) and (re.search(r'(?:от|при|чрез)$',pre(x)) or (NOUNV.search(m.group()) and pre(x).endswith('на')))),None);rest=[x for x in after if x is not att]
        if att is None:return None
        tgt=next((x for x in rest if x[2]!=att[2] and x[2]!='UN'),None)
        if tgt is None and loc and loc!=att[2]:tgt=(0,0,loc,None)
        if tgt is None:return None
    if att[2] not in PT or tgt[2] not in PT or att[2]==tgt[2]:return None
    return att[2],tgt,kind
def detect(t,loc):
    h=t[:320]
    if DELIV.search(h[:200]) and not STRONG.search(h):return None
    return _d2(t,loc)

DEFN=re.compile(r'^(?:атаката|атаките|нападението|нападенията|ударът|ударите|удара|обстрела|обстрелите|бомбардировката)$',re.I)
REFP=re.compile(r'(?:от|след|при|кадри|видео|заради|жертвите|последиците)\s*$',re.I)
def first_verb(h):
    for m in PHYS.finditer(h):
        wm=re.match(r'[А-Яа-я]+',h[m.start():]);w=wm.group() if wm else ''
        if DEFN.match(w) and REFP.search(h[max(0,m.start()-14):m.start()]):continue
        if re.match(r'^удар(?:на|ни|но|ния|ната|ните|ното)$',w,re.I):continue
        return m
    return None
