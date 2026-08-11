"""
dxcc.py - Risoluzione nominativo -> entita' DXCC con coordinate.

Due sorgenti dati:
  1. cty.dat  (formato AD1C / country-files.com) se presente: e' la sorgente
     preferita perche' contiene tutti i prefissi, gli override per singolo
     nominativo e le coordinate ufficiali di ogni entita'.
  2. Tabella interna di riserva (~270 entita') usata quando cty.dat non e'
     disponibile. Le coordinate sono i centri geografici approssimati.

NOTA: nel formato cty.dat la longitudine e' positiva a OVEST; qui viene
sempre convertita nella convenzione standard (positiva a EST).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

CTY_DOWNLOAD_URL = "https://www.country-files.com/bigcty/cty.dat"

# Suffissi portatili che NON indicano un cambio di entita'
_PORTABLE_SUFFIXES = {
    "P", "M", "MM", "AM", "QRP", "A", "B", "LH", "J", "R", "T",
    "BCN", "LGT", "AG", "AE", "KT", "N", "W", "QRPP",
}


@dataclass(frozen=True)
class DxccEntity:
    name: str
    primary_prefix: str
    lat: float
    lon: float          # positiva a EST
    continent: str = ""
    cq_zone: int = 0
    itu_zone: int = 0

    def __str__(self) -> str:
        return f"{self.name} ({self.primary_prefix})"


# --------------------------------------------------------------------------
# Tabella interna di riserva
# Formato: "prefissi|nome|primario|lat|lon(E+)|continente"
# --------------------------------------------------------------------------
_BUILTIN = """
1A|Sov. Mil. Order of Malta|1A|41.90|12.45|EU
3A|Monaco|3A|43.73|7.42|EU
3B8|Mauritius|3B8|-20.30|57.55|AF
3B9|Rodrigues Island|3B9|-19.70|63.42|AF
3B6,3B7|Agalega & St Brandon|3B6|-10.40|56.60|AF
3C0|Annobon Island|3C0|-1.43|5.63|AF
3C|Equatorial Guinea|3C|1.60|10.30|AF
3D2/C|Conway Reef|3D2/c|-21.75|174.60|OC
3D2/R|Rotuma Island|3D2/r|-12.50|177.07|OC
3D2|Fiji|3D2|-17.80|178.00|OC
3DA|Eswatini|3DA|-26.50|31.40|AF
3V|Tunisia|3V|34.00|9.50|AF
3W,XV|Vietnam|3W|16.00|107.00|AS
3X|Guinea|3X|10.40|-11.30|AF
3Y/B|Bouvet|3Y/b|-54.42|3.36|AF
3Y/P|Peter 1 Island|3Y/p|-68.80|-90.60|SA
4J,4K|Azerbaijan|4J|40.40|47.60|AS
4L|Georgia|4L|42.00|43.50|AS
4O|Montenegro|4O|42.50|19.30|EU
4S|Sri Lanka|4S|7.60|80.70|AS
4U1I|ITU HQ|4U1I|46.22|6.14|EU
4U1V|Vienna Intl Ctr|4U1V|48.20|16.37|EU
4W|Timor-Leste|4W|-8.80|125.70|OC
4X,4Z|Israel|4X|31.50|34.90|AS
5A|Libya|5A|27.00|17.00|AF
5B,C4,H2,P3,ZC4|Cyprus|5B|35.10|33.40|AS
5H,5I|Tanzania|5H|-6.00|35.00|AF
5N,5O|Nigeria|5N|9.50|8.00|AF
5R,5S|Madagascar|5R|-19.00|46.70|AF
5T|Mauritania|5T|20.00|-10.50|AF
5U|Niger|5U|17.00|9.00|AF
5V|Togo|5V|8.60|1.00|AF
5W|Samoa|5W|-13.80|-172.00|OC
5X|Uganda|5X|1.40|32.40|AF
5Y,5Z|Kenya|5Z|0.30|37.80|AF
6W,6V|Senegal|6W|14.40|-14.50|AF
6Y|Jamaica|6Y|18.10|-77.30|NA
7O|Yemen|7O|15.50|47.50|AS
7P|Lesotho|7P|-29.60|28.30|AF
7Q|Malawi|7Q|-13.30|34.30|AF
7X|Algeria|7X|28.00|3.00|AF
8P|Barbados|8P|13.20|-59.50|NA
8Q|Maldives|8Q|3.50|73.20|AS
8R|Guyana|8R|5.00|-58.80|SA
9A|Croatia|9A|45.20|15.90|EU
9G|Ghana|9G|7.90|-1.00|AF
9H|Malta|9H|35.90|14.40|EU
9J|Zambia|9J|-14.40|28.30|AF
9K|Kuwait|9K|29.30|47.70|AS
9L|Sierra Leone|9L|8.50|-11.80|AF
9M6,9M8,9W6,9W8|East Malaysia|9M6|4.50|116.00|OC
9M,9W|West Malaysia|9M2|3.90|102.30|AS
9N|Nepal|9N|28.30|84.00|AS
9Q,9O,9P,9S,9T|Dem. Rep. of Congo|9Q|-3.00|23.00|AF
9U|Burundi|9U|-3.40|29.90|AF
9V|Singapore|9V|1.35|103.80|AS
9X|Rwanda|9X|-1.95|29.90|AF
9Y,9Z|Trinidad & Tobago|9Y|10.50|-61.30|SA
A2|Botswana|A2|-22.30|24.70|AF
A3|Tonga|A3|-21.20|-175.20|OC
A4|Oman|A4|21.00|57.00|AS
A5|Bhutan|A5|27.40|90.40|AS
A6|United Arab Emirates|A6|24.30|54.40|AS
A7|Qatar|A7|25.30|51.20|AS
A9|Bahrain|A9|26.10|50.50|AS
AP,AQ,AR,AS|Pakistan|AP|30.00|70.00|AS
BV9P|Pratas Island|BV9P|20.70|116.70|AS
BV|Taiwan|BV|23.80|121.00|AS
BS7|Scarborough Reef|BS7|15.10|117.80|AS
B,3H,3I,3J,3K,3L,3M,3N,3O,3P,3Q,3R,3S,3T,3U,XS|China|BY|35.00|105.00|AS
C2|Nauru|C2|-0.53|166.90|OC
C3|Andorra|C3|42.50|1.50|EU
C5|The Gambia|C5|13.40|-15.40|AF
C6|Bahamas|C6|24.30|-76.50|NA
C8,C9|Mozambique|C9|-18.00|35.00|AF
CE0X|San Felix & San Ambrosio|CE0X|-26.30|-80.10|SA
CE0Y|Easter Island|CE0Y|-27.10|-109.40|SA
CE0Z|Juan Fernandez Islands|CE0Z|-33.60|-78.80|SA
CE9,KC4,8J1,DP0,RI1AN,VP8/a|Antarctica|CE9|-75.00|0.00|AN
CE,CA,CB,CD,XQ,XR,3G|Chile|CE|-33.50|-70.70|SA
CN,5C,5D,5E,5F,5G|Morocco|CN|32.00|-6.00|AF
CO,CM,CL,T4|Cuba|CM|21.50|-79.50|NA
CP|Bolivia|CP|-16.50|-68.10|SA
CQ3,CT3,CR3,CS3|Madeira Islands|CT3|32.75|-16.95|AF
CT,CQ,CR,CS|Portugal|CT|39.50|-8.00|EU
CU|Azores|CU|38.60|-28.00|EU
CV,CW,CX|Uruguay|CX|-33.00|-56.00|SA
CY0|Sable Island|CY0|43.93|-60.00|NA
CY9|St. Paul Island|CY9|47.20|-60.15|NA
D2,D3|Angola|D2|-12.00|17.50|AF
D4|Cape Verde|D4|15.90|-23.70|AF
D6|Comoros|D6|-11.70|43.30|AF
DA,DB,DC,DD,DE,DF,DG,DH,DJ,DK,DL,DM,DN,DO,DP,DQ,DR,Y2,Y3,Y4,Y5,Y6,Y7,Y8,Y9|Germany|DL|51.00|10.00|EU
DU,DV,DW,DX,DY,DZ,4D,4E,4F,4G,4H,4I|Philippines|DU|13.00|122.00|OC
E3|Eritrea|E3|15.30|38.90|AF
E4|Palestine|E4|31.50|34.50|AS
E5/N|North Cook Islands|E5/n|-10.90|-165.80|OC
E5|South Cook Islands|E5/s|-21.20|-159.80|OC
E6|Niue|E6|-19.05|-169.90|OC
E7|Bosnia-Herzegovina|E7|44.00|18.00|EU
EA6,EB6,EC6,ED6,EE6,EF6,EG6,EH6|Balearic Islands|EA6|39.60|2.90|EU
EA8,EB8,EC8,ED8,EE8,EF8,EG8,EH8|Canary Islands|EA8|28.30|-15.80|AF
EA9,EB9,EC9,ED9,EE9,EF9,EG9,EH9|Ceuta & Melilla|EA9|35.90|-5.30|AF
EA,EB,EC,ED,EE,EF,EG,EH,AM,AN,AO|Spain|EA|40.30|-3.70|EU
EI,EJ|Ireland|EI|53.20|-8.00|EU
EK|Armenia|EK|40.20|44.90|AS
EL|Liberia|EL|6.50|-9.50|AF
EP,EQ,9B,9C,9D|Iran|EP|32.00|53.00|AS
ER|Moldova|ER|47.00|28.90|EU
ES,ER2|Estonia|ES|58.70|25.50|EU
ET|Ethiopia|ET|9.00|39.00|AF
EU,EV,EW|Belarus|EU|53.70|27.90|EU
EX|Kyrgyzstan|EX|41.50|74.60|AS
EY|Tajikistan|EY|38.80|71.00|AS
EZ|Turkmenistan|EZ|39.00|59.00|AS
F,TM,TP,TQ,TV,HW,HX,HY|France|F|46.50|2.50|EU
FG,TO|Guadeloupe|FG|16.20|-61.50|NA
FH|Mayotte|FH|-12.80|45.20|AF
FJ|Saint Barthelemy|FJ|17.90|-62.80|NA
FK/C|Chesterfield Islands|FK/c|-19.87|158.40|OC
FK|New Caledonia|FK|-21.50|165.50|OC
FM|Martinique|FM|14.65|-61.00|NA
FO/A|Austral Islands|FO/a|-23.35|-149.50|OC
FO/C|Clipperton Island|FO/c|10.30|-109.22|NA
FO/M|Marquesas Islands|FO/m|-9.00|-139.50|OC
FO|French Polynesia|FO|-17.60|-149.40|OC
FP|St. Pierre & Miquelon|FP|46.80|-56.20|NA
FR|Reunion Island|FR|-21.10|55.50|AF
FS|Saint Martin|FS|18.07|-63.05|NA
FT/E|Europa Island|FT/e|-22.35|40.35|AF
FT/G|Glorioso Islands|FT/g|-11.55|47.30|AF
FT/J|Juan de Nova|FT/j|-17.05|42.70|AF
FT/T|Tromelin Island|FT/t|-15.90|54.50|AF
FT/W|Crozet Island|FT/w|-46.40|51.90|AF
FT/X|Kerguelen Islands|FT/x|-49.35|70.20|AF
FT/Z|Amsterdam & St. Paul|FT/z|-37.80|77.50|AF
FW|Wallis & Futuna|FW|-13.30|-176.20|OC
FY|French Guiana|FY|4.00|-53.00|SA
GD,GT,MD,MT,2D|Isle of Man|GD|54.20|-4.50|EU
GI,GN,MI,MN,2I|Northern Ireland|GI|54.60|-6.50|EU
GJ,GH,MJ,MH,2J|Jersey|GJ|49.20|-2.10|EU
GM,GS,MM,MS,2M|Scotland|GM|56.80|-4.20|EU
GU,GP,MU,MP,2U|Guernsey|GU|49.45|-2.58|EU
GW,GC,MW,MC,2W|Wales|GW|52.30|-3.70|EU
G,M,2E|England|G|52.50|-1.50|EU
H4|Solomon Islands|H4|-9.40|160.00|OC
H40|Temotu Province|H40|-10.70|165.80|OC
HA,HG|Hungary|HA|47.20|19.40|EU
HB0|Liechtenstein|HB0|47.15|9.55|EU
HB,HE|Switzerland|HB|46.90|8.20|EU
HC8,HD8|Galapagos Islands|HC8|-0.70|-90.30|SA
HC,HD|Ecuador|HC|-1.50|-78.50|SA
HH,4V|Haiti|HH|19.00|-72.40|NA
HI|Dominican Republic|HI|18.80|-70.20|NA
HK0/A|Malpelo Island|HK0/a|4.00|-81.60|SA
HK0|San Andres & Providencia|HK0/m|12.55|-81.70|NA
HK,HJ,5J,5K|Colombia|HK|4.00|-73.00|SA
HL,DS,DT,6K,6L,6M,6N|Republic of Korea|HL|36.50|127.80|AS
HO,HP,H3,H8,H9,3E,3F|Panama|HP|8.50|-80.00|NA
HQ,HR|Honduras|HR|14.70|-86.50|NA
HS,E2|Thailand|HS|15.00|101.00|AS
HV|Vatican|HV|41.90|12.45|EU
HZ,7Z,8Z|Saudi Arabia|HZ|24.00|45.00|AS
IS0,IM0,IW0U,IW0T|Sardinia|IS0|40.10|9.00|EU
IT9,IB9,ID9,IE9,IF9,IH9,II9,IJ9,IO9,IQ9,IR9,IU9,IW9,IY9,IZ9|Sicily|IT9|37.50|14.20|EU
I,IA,IB,IC,ID,IE,IF,IH,II,IK,IN,IO,IQ,IR,IU,IV,IW,IY,IZ|Italy|I|42.80|12.60|EU
J2,J20|Djibouti|J2|11.60|43.10|AF
J3|Grenada|J3|12.10|-61.70|NA
J5|Guinea-Bissau|J5|12.00|-15.00|AF
J6|St. Lucia|J6|13.90|-61.00|NA
J7|Dominica|J7|15.40|-61.30|NA
J8|St. Vincent|J8|13.20|-61.20|NA
JD1/M|Minami Torishima|JD1/m|24.30|154.00|OC
JD1|Ogasawara|JD1/o|27.10|142.20|AS
JA,JE,JF,JG,JH,JI,JJ,JK,JL,JM,JN,JO,JP,JQ,JR,JS,7J,7K,7L,7M,7N,8J,8K,8L,8M,8N|Japan|JA|36.00|139.00|AS
JT,JU,JV|Mongolia|JT|46.90|103.80|AS
JW|Svalbard|JW|78.20|15.60|EU
JX|Jan Mayen|JX|71.00|-8.30|EU
JY|Jordan|JY|31.20|36.50|AS
KG4|Guantanamo Bay|KG4|19.90|-75.20|NA
KH0,AH0,NH0,WH0|Mariana Islands|KH0|15.20|145.70|OC
KH1,AH1,NH1,WH1|Baker & Howland|KH1|0.20|-176.50|OC
KH2,AH2,NH2,WH2|Guam|KH2|13.45|144.75|OC
KH3,AH3,NH3,WH3|Johnston Island|KH3|16.73|-169.53|OC
KH4,AH4,NH4,WH4|Midway Island|KH4|28.20|-177.40|OC
KH5,AH5,NH5,WH5|Palmyra & Jarvis|KH5|5.90|-162.10|OC
KH7K,AH7K,NH7K,WH7K|Kure Island|KH7K|28.40|-178.30|OC
KH6,KH7,AH6,AH7,NH6,NH7,WH6,WH7|Hawaii|KH6|21.30|-157.80|OC
KH8/S|Swains Island|KH8/s|-11.05|-171.08|OC
KH8,AH8,NH8,WH8|American Samoa|KH8|-14.30|-170.70|OC
KH9,AH9,NH9,WH9|Wake Island|KH9|19.30|166.60|OC
KL,AL,NL,WL,KL7|Alaska|KL|64.00|-150.00|NA
KP1,NP1,WP1|Navassa Island|KP1|18.40|-75.00|NA
KP2,NP2,WP2|US Virgin Islands|KP2|17.70|-64.80|NA
KP5,NP5,WP5|Desecheo Island|KP5|18.40|-67.50|NA
KP3,KP4,NP3,NP4,WP3,WP4|Puerto Rico|KP4|18.20|-66.50|NA
K,W,N,AA,AB,AC,AD,AE,AF,AG,AI,AJ,AK|United States|K|39.50|-98.00|NA
LA,LB,LC,LD,LE,LF,LG,LH,LI,LJ,LK,LL,LM,LN|Norway|LA|61.00|9.00|EU
LU,LO,LP,LQ,LR,LS,LT,LV,LW,AY,AZ,L2,L3,L4,L5,L6,L7,L8,L9|Argentina|LU|-34.60|-58.40|SA
LX|Luxembourg|LX|49.80|6.10|EU
LY|Lithuania|LY|55.30|23.90|EU
LZ|Bulgaria|LZ|42.70|25.30|EU
OA,OB,OC,4T|Peru|OA|-12.00|-77.00|SA
OD|Lebanon|OD|33.90|35.60|AS
OE|Austria|OE|47.60|14.10|EU
OH0|Aland Islands|OH0|60.20|20.00|EU
OJ0|Market Reef|OJ0|60.30|19.13|EU
OF,OG,OH,OI|Finland|OH|62.80|26.00|EU
OK,OL|Czech Republic|OK|49.80|15.50|EU
OM|Slovak Republic|OM|48.70|19.50|EU
ON,OO,OP,OQ,OR,OS,OT|Belgium|ON|50.70|4.60|EU
OU,OV,OZ,5P,5Q|Denmark|OZ|55.90|9.50|EU
OX,XP|Greenland|OX|72.00|-40.00|NA
OY|Faroe Islands|OY|62.00|-6.90|EU
P2|Papua New Guinea|P2|-6.00|147.00|OC
P4|Aruba|P4|12.50|-70.00|SA
P5|North Korea|P5|39.00|126.00|AS
PA,PB,PC,PD,PE,PF,PG,PH,PI|Netherlands|PA|52.20|5.50|EU
PJ2|Curacao|PJ2|12.20|-69.00|SA
PJ4|Bonaire|PJ4|12.20|-68.30|SA
PJ5,PJ6|Saba & St. Eustatius|PJ5|17.50|-63.20|NA
PJ7|Sint Maarten|PJ7|18.04|-63.06|NA
PY0F|Fernando de Noronha|PY0F|-3.85|-32.40|SA
PY0S|St. Peter & St. Paul|PY0S|0.92|-29.35|SA
PY0T|Trindade & Martim Vaz|PY0T|-20.50|-29.30|SA
PP,PQ,PR,PS,PT,PU,PV,PW,PX,PY,ZV,ZW,ZX,ZY,ZZ|Brazil|PY|-15.80|-47.90|SA
PZ|Suriname|PZ|5.80|-55.20|SA
R1FJ|Franz Josef Land|R1FJ|80.60|54.90|EU
S0|Western Sahara|S0|24.50|-13.00|AF
S2|Bangladesh|S2|23.70|90.40|AS
S5|Slovenia|S5|46.10|14.80|EU
S7|Seychelles|S7|-4.60|55.50|AF
S9|Sao Tome & Principe|S9|0.30|6.70|AF
SM,SA,SB,SC,SD,SE,SF,SG,SH,SI,SJ,SK,SL,7S,8S|Sweden|SM|62.00|15.00|EU
SP,SN,SO,SQ,SR,3Z,HF|Poland|SP|52.10|19.40|EU
ST|Sudan|ST|15.60|32.50|AF
SU|Egypt|SU|27.00|30.00|AF
SV/A|Mount Athos|SV/a|40.20|24.30|EU
SV5,J45|Dodecanese|SV5|36.40|28.20|EU
SV9,J49|Crete|SV9|35.20|24.90|EU
SV,SW,SX,SY,SZ,J4|Greece|SV|39.00|22.00|EU
T2|Tuvalu|T2|-8.50|179.20|OC
T30|Western Kiribati|T30|1.40|173.00|OC
T31|Central Kiribati|T31|-3.90|-174.80|OC
T32|Eastern Kiribati|T32|1.90|-157.40|OC
T33|Banaba Island|T33|-0.87|169.50|OC
T5,6O|Somalia|T5|5.00|46.00|AF
T7|San Marino|T7|43.94|12.45|EU
T8|Palau|T8|7.50|134.60|OC
TA,TB,TC,YM|Turkey|TA|39.00|35.00|AS
TF|Iceland|TF|64.90|-19.00|EU
TG,TD|Guatemala|TG|15.50|-90.30|NA
TI9|Cocos Island|TI9|5.53|-87.05|NA
TI,TE|Costa Rica|TI|9.90|-84.00|NA
TJ|Cameroon|TJ|5.70|12.70|AF
TK|Corsica|TK|42.10|9.10|EU
TL|Central African Republic|TL|6.60|20.90|AF
TN|Republic of the Congo|TN|-1.00|15.50|AF
TR|Gabon|TR|-0.80|11.60|AF
TT|Chad|TT|15.00|19.00|AF
TU|Cote d'Ivoire|TU|7.50|-5.50|AF
TY|Benin|TY|9.50|2.30|AF
TZ|Mali|TZ|17.50|-4.00|AF
UA9,UA8,UA0,UB9,UB8,UB0,UC9,UC8,UC0,UD9,UD8,UD0,UE9,UE8,UE0,UF9,UF8,UF0,UG9,UG8,UG0,UH9,UH8,UH0,UI9,UI8,UI0,RA9,RA8,RA0,RC9,RC8,RC0,RD9,RD8,RD0,RE9,RE8,RE0,RF9,RF8,RF0,RG9,RG8,RG0,RJ9,RJ8,RJ0,RK9,RK8,RK0,RL9,RL8,RL0,RM9,RM8,RM0,RN9,RN8,RN0,RO9,RO8,RO0,RQ9,RQ8,RQ0,RT9,RT8,RT0,RU9,RU8,RU0,RV9,RV8,RV0,RW9,RW8,RW0,RX9,RX8,RX0,RY9,RY8,RY0,RZ9,RZ8,RZ0,R9,R8,R0|Asiatic Russia|UA9|62.00|105.00|AS
UA2,RA2|Kaliningrad|UA2|54.70|20.50|EU
UA,UB,UC,UD,UE,UF,UG,UH,UI,RA,RC,RD,RE,RF,RG,RJ,RK,RL,RM,RN,RO,RQ,RT,RU,RV,RW,RX,RY,RZ,R|European Russia|UA|55.70|37.60|EU
UK|Uzbekistan|UK|41.30|64.60|AS
UN,UO,UP,UQ|Kazakhstan|UN|48.00|68.00|AS
UR,UT,UU,UV,UW,UX,UY,UZ,EM,EN,EO|Ukraine|UR|49.50|31.50|EU
V2|Antigua & Barbuda|V2|17.10|-61.80|NA
V3|Belize|V3|17.20|-88.70|NA
V4|St. Kitts & Nevis|V4|17.30|-62.70|NA
V5|Namibia|V5|-22.00|17.00|AF
V6|Micronesia|V6|6.90|158.20|OC
V7|Marshall Islands|V7|7.10|171.40|OC
V8|Brunei Darussalam|V8|4.50|114.60|OC
VE,VA,VB,VC,VD,VF,VG,VO,VX,VY,CF,CG,CH,CI,CJ,CK,XJ,XK,XL,XM,XN,XO|Canada|VE|56.00|-96.00|NA
VK0/H|Heard Island|VK0H|-53.10|73.50|AF
VK0/M|Macquarie Island|VK0M|-54.50|158.90|OC
VK9C|Cocos (Keeling) Islands|VK9C|-12.20|96.80|OC
VK9L|Lord Howe Island|VK9L|-31.50|159.10|OC
VK9M|Mellish Reef|VK9M|-17.40|155.85|OC
VK9N|Norfolk Island|VK9N|-29.03|167.95|OC
VK9W|Willis Island|VK9W|-16.30|150.00|OC
VK9X|Christmas Island|VK9X|-10.50|105.60|OC
VK,AX,VH,VI,VJ,VL,VM,VN,VZ|Australia|VK|-25.00|134.00|OC
VP2E|Anguilla|VP2E|18.20|-63.05|NA
VP2M|Montserrat|VP2M|16.75|-62.20|NA
VP2V|British Virgin Islands|VP2V|18.40|-64.60|NA
VP5,VQ5|Turks & Caicos Islands|VP5|21.80|-71.80|NA
VP6/D|Ducie Island|VP6/d|-24.67|-124.80|OC
VP6|Pitcairn Island|VP6|-25.07|-130.10|OC
VP8/G|South Georgia Island|VP8/g|-54.30|-36.50|SA
VP8/O|South Orkney Islands|VP8/o|-60.60|-45.60|SA
VP8/H|South Shetland Islands|VP8/h|-62.00|-58.50|SA
VP8/S|South Sandwich Islands|VP8/s|-57.80|-26.50|SA
VP8|Falkland Islands|VP8|-51.70|-57.90|SA
VP9|Bermuda|VP9|32.30|-64.75|NA
VQ9|Chagos Islands|VQ9|-7.30|72.40|AF
VR,VR2|Hong Kong|VR|22.30|114.20|AS
VU4|Andaman & Nicobar Islands|VU4|11.70|92.70|AS
VU7|Lakshadweep Islands|VU7|10.60|72.60|AS
VU,AT,AU,AV,AW,8T,8U,8V,8W,8X,8Y|India|VU|21.00|78.00|AS
XE,XA,XB,XC,XD,XF,4A,4B,4C,6D,6E,6F,6G,6H,6I,6J|Mexico|XE|23.00|-102.00|NA
XF4|Revillagigedo|XF4|18.80|-110.98|NA
XT|Burkina Faso|XT|12.40|-1.50|AF
XU|Cambodia|XU|12.60|105.00|AS
XW|Laos|XW|18.00|103.00|AS
XX9|Macao|XX9|22.20|113.55|AS
XY,XZ|Myanmar|XZ|21.00|96.00|AS
YA,T6|Afghanistan|YA|33.90|67.70|AS
YB,YC,YD,YE,YF,YG,YH,7A,7B,7C,7D,7E,7F,7G,7H,7I,8A,8B,8C,8D,8E,8F,8G,8H,8I|Indonesia|YB|-2.00|118.00|OC
YI|Iraq|YI|33.20|43.70|AS
YJ|Vanuatu|YJ|-16.00|168.00|OC
YK,6C|Syria|YK|35.00|38.50|AS
YL|Latvia|YL|56.90|24.60|EU
YN,H6,H7,HT|Nicaragua|YN|12.90|-85.20|NA
YO,YP,YQ,YR|Romania|YO|45.90|25.00|EU
YS,HU|El Salvador|YS|13.80|-88.90|NA
YT,YU|Serbia|YU|44.20|20.80|EU
YV,YW,YX,YY,4M|Venezuela|YV|7.00|-66.00|SA
Z2|Zimbabwe|Z2|-19.00|29.90|AF
Z3|North Macedonia|Z3|41.60|21.70|EU
Z6|Kosovo|Z6|42.60|20.90|EU
Z8|South Sudan|Z8|6.90|31.30|AF
ZA|Albania|ZA|41.10|20.00|EU
ZB2|Gibraltar|ZB2|36.14|-5.35|EU
ZD7|St. Helena|ZD7|-15.95|-5.70|AF
ZD8|Ascension Island|ZD8|-7.95|-14.40|AF
ZD9|Tristan da Cunha & Gough|ZD9|-37.10|-12.30|AF
ZF|Cayman Islands|ZF|19.30|-81.20|NA
ZK3|Tokelau Islands|ZK3|-9.20|-171.80|OC
ZL7|Chatham Islands|ZL7|-44.00|-176.50|OC
ZL8|Kermadec Islands|ZL8|-29.25|-177.90|OC
ZL9|New Zealand Subantarctic|ZL9|-50.80|166.10|OC
ZL,ZM|New Zealand|ZL|-41.00|174.00|OC
ZP|Paraguay|ZP|-25.30|-57.60|SA
ZS8|Prince Edward & Marion|ZS8|-46.90|37.75|AF
ZS,ZR,ZT,ZU,H5|South Africa|ZS|-29.00|25.00|AF
"""


def _load_builtin() -> Dict[str, DxccEntity]:
    table: Dict[str, DxccEntity] = {}
    for line in _BUILTIN.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        prefixes, name, primary, lat, lon, cont = line.split("|")
        ent = DxccEntity(
            name=name,
            primary_prefix=primary,
            lat=float(lat),
            lon=float(lon),
            continent=cont,
        )
        for p in prefixes.split(","):
            p = p.strip().upper()
            if p:
                table[p] = ent
    return table


# --------------------------------------------------------------------------
# Parser cty.dat
# --------------------------------------------------------------------------

_CTY_HEADER_RE = re.compile(
    r"^(?P<name>[^:]+):\s*(?P<cq>\d+):\s*(?P<itu>\d+):\s*(?P<cont>\w+):\s*"
    r"(?P<lat>[-\d.]+):\s*(?P<lon>[-\d.]+):\s*(?P<utc>[-\d.]+):\s*(?P<pfx>[^:]*):"
)

# es.  =W1AW(5)[8]<41.71/-72.73>{NA}~-5~   oppure   VP2E<18.22/-63.06>
_CTY_MOD_RE = re.compile(
    r"^(?P<pfx>[^(\[<{~]+)"
    r"(?:\((?P<cq>\d+)\))?"
    r"(?:\[(?P<itu>\d+)\])?"
    r"(?:<(?P<lat>[-\d.]+)/(?P<lon>[-\d.]+)>)?"
    r"(?:\{(?P<cont>\w+)\})?"
    r"(?:~(?P<utc>[-\d.]+)~)?"
)


def parse_cty_dat(text: str) -> Tuple[Dict[str, DxccEntity], Dict[str, DxccEntity]]:
    """
    Interpreta il contenuto di cty.dat.

    Restituisce (prefissi, nominativi_esatti).
    Le voci che in cty.dat iniziano con '=' sono override per nominativo esatto.
    """
    prefixes: Dict[str, DxccEntity] = {}
    exact: Dict[str, DxccEntity] = {}

    record: List[str] = []
    for raw in text.splitlines():
        if not raw.strip():
            continue
        record.append(raw)
        if raw.rstrip().endswith(";"):
            _parse_cty_record("\n".join(record), prefixes, exact)
            record = []
    if record:
        _parse_cty_record("\n".join(record), prefixes, exact)
    return prefixes, exact


def _parse_cty_record(block: str, prefixes: Dict[str, DxccEntity],
                      exact: Dict[str, DxccEntity]) -> None:
    lines = block.split("\n")
    m = _CTY_HEADER_RE.match(lines[0])
    if not m:
        return
    base = DxccEntity(
        name=m.group("name").strip(),
        primary_prefix=m.group("pfx").strip(),
        lat=float(m.group("lat")),
        lon=-float(m.group("lon")),          # cty.dat: ovest positivo -> est positivo
        continent=m.group("cont").strip(),
        cq_zone=int(m.group("cq")),
        itu_zone=int(m.group("itu")),
    )

    body = " ".join(lines[1:]).strip().rstrip(";")
    for token in body.split(","):
        token = token.strip()
        if not token:
            continue
        is_exact = token.startswith("=")
        if is_exact:
            token = token[1:]
        mm = _CTY_MOD_RE.match(token)
        if not mm:
            continue
        pfx = mm.group("pfx").strip().upper()
        if not pfx:
            continue
        ent = base
        if mm.group("lat") and mm.group("lon"):
            ent = DxccEntity(
                name=base.name,
                primary_prefix=base.primary_prefix,
                lat=float(mm.group("lat")),
                lon=-float(mm.group("lon")),
                continent=mm.group("cont") or base.continent,
                cq_zone=int(mm.group("cq")) if mm.group("cq") else base.cq_zone,
                itu_zone=int(mm.group("itu")) if mm.group("itu") else base.itu_zone,
            )
        if is_exact:
            exact[pfx] = ent
        else:
            prefixes[pfx] = ent


# --------------------------------------------------------------------------
# Estrazione prefisso dal nominativo
# --------------------------------------------------------------------------

def normalize_call(call: str) -> str:
    """Ripulisce un nominativo: maiuscolo, senza spazi, senza caratteri strani."""
    if not call:
        return ""
    call = call.strip().upper()
    call = re.sub(r"[^A-Z0-9/]", "", call)
    return call.strip("/")


def effective_call(call: str) -> str:
    """
    Riduce un nominativo con barre alla parte che determina l'entita' DXCC.

      IK0ABC/P     -> IK0ABC
      F/IK0ABC     -> F/IK0ABC     (il prefisso F comanda)
      VP2E/K1ABC   -> VP2E
      IK0ABC/3     -> IK3ABC
      KH6/DL1XYZ   -> KH6
    """
    call = normalize_call(call)
    if "/" not in call:
        return call

    parts = [p for p in call.split("/") if p]
    if not parts:
        return call

    # elimina i suffissi portatili non significativi
    meaningful = [p for p in parts if p not in _PORTABLE_SUFFIXES]
    if not meaningful:
        return parts[0]

    # rimappatura di area:  IK0ABC/3
    if len(meaningful) == 2 and meaningful[1].isdigit() and len(meaningful[1]) == 1:
        base = meaningful[0]
        m = re.match(r"^([A-Z0-9]*?[A-Z]+)(\d)(.*)$", base)
        if m:
            return f"{m.group(1)}{meaningful[1]}{m.group(3)}"
        return base

    if len(meaningful) == 1:
        return meaningful[0]

    # con due o piu' parti significative vince quella piu' corta (il prefisso
    # ospite), es. VP2E/K1ABC oppure KH6/DL1XYZ
    meaningful.sort(key=len)
    if len(meaningful[0]) == len(meaningful[1]):
        return meaningful[0]
    return meaningful[0]


# --------------------------------------------------------------------------
# Resolver
# --------------------------------------------------------------------------

class DxccResolver:
    """Risolve un nominativo nella sua entita' DXCC."""

    def __init__(self, cty_path: Optional[str] = None) -> None:
        self._builtin = _load_builtin()
        self._prefixes: Dict[str, DxccEntity] = {}
        self._exact: Dict[str, DxccEntity] = {}
        self.source = "interna"
        self.cty_path: Optional[str] = None
        if cty_path:
            try:
                self.load_cty(cty_path)
            except Exception:
                pass

    # -- caricamento ------------------------------------------------------
    def load_cty(self, path: str) -> int:
        """Carica un cty.dat. Restituisce il numero di prefissi caricati."""
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        prefixes, exact = parse_cty_dat(text)
        if not prefixes:
            raise ValueError("cty.dat non valido o vuoto")
        self._prefixes = prefixes
        self._exact = exact
        self.cty_path = os.path.abspath(path)
        self.source = f"cty.dat ({len(prefixes)} prefissi)"
        return len(prefixes)

    @property
    def has_cty(self) -> bool:
        return bool(self._prefixes)

    # -- lookup -----------------------------------------------------------
    def lookup(self, call: str) -> Optional[DxccEntity]:
        """Restituisce l'entita' DXCC di un nominativo, oppure None."""
        raw = normalize_call(call)
        if not raw:
            return None

        # 1. override per nominativo esatto (solo cty.dat)
        if raw in self._exact:
            return self._exact[raw]

        eff = effective_call(raw)
        if eff in self._exact:
            return self._exact[eff]

        # 2. match sul prefisso piu' lungo
        ent = self._longest_match(eff, self._prefixes) if self._prefixes else None
        if ent is None:
            ent = self._longest_match(eff, self._builtin)
        if ent is None and eff != raw:
            ent = self._longest_match(raw, self._prefixes or self._builtin)
        return ent

    @staticmethod
    def _longest_match(call: str, table: Dict[str, DxccEntity]) -> Optional[DxccEntity]:
        if not table:
            return None
        for n in range(min(len(call), 8), 0, -1):
            key = call[:n]
            ent = table.get(key)
            if ent is not None:
                return ent
        return None
