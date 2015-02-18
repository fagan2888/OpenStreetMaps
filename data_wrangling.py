#!/usr/bin/python
# -*- coding: utf-8 -*-
'''
Clean and reshape data from Open Street maps and
insert it in mongo DB.  

Created on 29/01/2015
'''

__author__='ucaiado'

#import libraries
import re
import xml.etree.cElementTree as ET
import pprint
from collections import defaultdict
import codecs
import json
import datetime
from dbfpy import dbf
from unidecode import unidecode



#define some regular expressions checks
lower = re.compile(r'^([a-z]|_)*$')
lower_colon = re.compile(r'^([a-z]|_)*:([a-z]|_)*$')
problemchars = re.compile(r'[=\+/&<>;\'"\?%#$@\,\. \t\r\n]')
problemchars2 = re.compile(r'[=\+/&<>;\'"\?%#$@\,\ \t\r\n]')
street_type_re = re.compile(r'([^\s]+)', re.IGNORECASE)




# variables to correct street names
expected =['avenida',"alameda",'largo','travessa',u'praça', 'via','viaduto','viela', 'estrada', 'rodovia', 'rua','passagem']

mapping = {  'av': u'avenida',
             'al': u"alameda",
             'lgo': u'largo',
             'praca': u'pra\xe7a',
             'r': u'rua',
             'rd': u'rodovia'
            }

mapping_title = {'cel': u'coronel',
             'dr': u"doutor",
             'eng': u'engenheiro',
             'pres': u'presidente',
             'prof': u'professor',
             'sen': u'senador'
            }

# variables to correct cities names
d_wrongCitiesNames={  'aruja': u"Arujá",
 'itu': u"Itú",
 'maua': u"Mauá",
 'sao bernardo do campo': u"São Bernado do Campo",
 'sao jose dos campos': u"São José dos Campos",
 'sao paolo': u"São Paulo",
 'sao paulo': u"São Paulo",
 'sao vicente': u"São Vicente",
u's\xe3o paulo - sp': u"São Paulo",
u's\xe3o paulo/sp': u"São Paulo", 
 'guaruja': u"Guarujá",
u'ibi\xfana-sp': u"Ibiúna" ,
u'service': None,
u'alum\xednio': None,
u'mooca': None
}

# variables to create docs to Mongo
CREATED = [ "version", "changeset", "timestamp", "user", "uid"]
NODE = ["id","visible","amenity","cuisine","name","phone"]

#track corrections
TRACK_STREETS=0
TRACK_CITIES=0


'''
Begin of Help Functions
'''
def aggregate(db, pipeline):
    '''Return filtered data according to pipeline passed'''        
    result = db.aggregate(pipeline)  
    return result['result']


def key_type(element, keys):
    '''
    Check if there is any problem in the "k" attribute 
    for each tag from XML. Return a updated dictionary
    with the count of it.

    element: element from a Element Tree object
    keys: a dictionary with the previous counting
    '''	
    if element.tag == "tag":
        s=element.attrib['k']
        if problemchars.search(s): keys['problemchars']+=1 
        elif lower_colon.search(s):keys['lower_colon']+=1
        elif lower.search(s):keys['lower']+=1
        else: keys['other']+=1

        
    return keys

def get_user(element,users):
    '''
    Count the number of unique users on the XML file. 
    element: element from a Element Tree object
    users: is a set of users already registered
    '''	
    if element.tag == "node":
        users.add(element.attrib['uid'])

        
    return users

def is_street_name(elem):
    '''
    Check if the XML element passed reffer to a street name
    '''    
    return (((elem.attrib['k']).lower() == "addr:street") )

def is_city_name(elem):
    '''
    Check if the XML element passed reffer to a city name
    '''    
    return (((elem.attrib['k']).lower() == "addr:city") )

def audit_street_type(street_types, street_name):
    '''
    Update street_types dictionary with the street name passed where can exist 
    some issue. 
    '''
    #Check the first word in the name
    m = street_type_re.search(street_name)
    if m:
        street_type = m.group().lower()
        if street_type not in expected:
            street_types[street_type].add(street_name)
        #check the second word, when it exists. In portuguese, commonly 
        #the second word in the street name can be shortened as well
        l_names=street_name.split()
        if len(l_names)>1:
            s=l_names[1].lower()
            if '.' == s[-1]: s = s[:-1]
            if s in mapping_title:
                 street_types[street_type].add(street_name)


def update_name_and_titles(name, mapping, mapping_title):
    '''
    Check for shortened words in the street name, replacing it by the complete
    word. Return the string corrected when needed.
    '''    
    #define abort control
    i_abort=0
    
    #take the first and second word from the string passed
    l_names=name.split()
    s_1=l_names[0].lower()
    if len(l_names)>1:s_2=name.split()[1].lower()
    else:s_2=' '


    #take off the dot from the strings, if it is presentes
    if '.' in s_2[-1]: s_b = s_2[:-1]
    else:s_b = s_2
    if '.' in s_1[-1]: s_a = s_1[:-1]  
    else:s_a = s_1

    #check if the first word is a street type valid
    if s_a not in mapping: i_abort+=1
    else: s_a=mapping[s_a]

    #check if the second string should be used
    if s_b in mapping_title: 
        s_c="{} {}".format(s_a, mapping_title[s_b])
    else:
        i_abort+=1
        s_c=s_a
        s_2=''

    #return none if there is no point in correct the name
    if i_abort==2: return None
    
    #extract the street name from the string passed
    name=name[(len(s_1)+len(s_2)+1):len(name)].lower().strip()

    #look for errors in the string
    if problemchars2.search(name):
        l=[x for x in problemchars2.findall(name) if x !=' ']
        if l: name=name.split(l[0])[0]

    #encode correctly the name
    try:
        name=(u"{} {}".format(s_c,unicode(name.strip(), 'utf8'))).title() 
    except UnicodeDecodeError :
        name=(u"{} {}".format(s_c,unicode(name.strip(), 'latin1'))).title()
    except TypeError:
        name=(u"{} {}".format(s_c,name.strip())).title()         

    return name   




def shape_element(element,d_streetName,d_wrongCitiesNames=d_wrongCitiesNames):
    '''
    Reshape the element passed to fit into mongodb. Return a dictionary with the
    data restructured. If it is not possible to correct, return None.
    element: xml element object
    d_streetName: a dictionary with corrected streets names
    d_wrongCitiesNames: a dict with corrected cities names
    '''
    node={}
    global TRACK_STREETS, TRACK_CITIES
    if element.tag == "node" or element.tag == "way" :
        node['type'] = element.tag
        for tag in element.iter("tag"):
            #check problemns
            if 'k' not in tag.attrib: continue
            s = tag.attrib['k']
            if s.count(":")>1: continue
            if problemchars.search(s): continue 
            #set the name to be insert in the dict
            better_name=tag.attrib['v'].lower()               
            #check k refer to address
            if s[:5]=='addr:':
                #initialize address dict in node dict
                if 'address' not in node: node['address']={}
                if  is_street_name(tag):
                    #if is needed, correct street name
                    if better_name in  d_streetName:
                        better_name=d_streetName[better_name]
                    if not better_name: continue
                    else: TRACK_STREETS+=1
                elif is_city_name(tag):
                    #if is needed, correct city name
                    if better_name in  d_wrongCitiesNames:
                        better_name=d_wrongCitiesNames[better_name] 
                    if not better_name: continue
                    else: TRACK_CITIES+=1
                #set the value to address node  
                node['address'][s[5:]]=better_name.title()
            else:
                #set node if it is nor about adress
                node[s]=better_name.title()

        for tag in element.iter("nd"):
            if 'node_refs' not in node: node['node_refs']=[]
            if 'ref' in tag.attrib: node['node_refs'].append(tag.attrib['ref'])
        #fill last informations
        for key, val in element.attrib.items():
            if key in NODE:
                node[key] = val
            if key in CREATED:
               if 'created' not in node: node['created']={}
               node['created'][key] = val 
            if key == 'lat':
               if 'pos' not in node: node['pos']=[0,0]
               node['pos'][0]=float(val)
            if key == 'lon':
               if 'pos' not in node: node['pos']=[0,0]
               node['pos'][1]=float(val)
        
        return node
    else:
        return None



def audit(osmfile):
    '''
    Return a dictionary with potential wrong or shortened street names in
    the OSM file.

    The streets in Brazil commonly are named by military and political 
    authorities names. Besides the first word, that is related to the street type, 
    it also can present a second word optionally related to the  authority title, 
    as Colonel or Senator, for instance.
    '''    
    osm_file = open(osmfile, "r")
    street_types = defaultdict(set)
    for event, elem in ET.iterparse(osm_file, events=("start",)):

        if elem.tag == "node" or elem.tag == "way":
            for tag in elem.iter("tag"):
                if is_street_name(tag):
                    audit_street_type(street_types, tag.attrib['v'])
            elem.clear() # discard the element

    return street_types


'''
End of Help Functions
'''

def count_tags(filename):
    '''
    Count the number of each tag presented in the XML file 
    passed. An Open Street Maps XML file is expected.
    Return a dictionary with the counting of each tag.
    '''
    d={}
    for event, elem in ET.iterparse(filename):
        if event == 'end':
            if elem.tag not in d: d[elem.tag]=1
            else: d[elem.tag]+=1
        # discard the element to preserv RAM
        elem.clear() 
            
    return d


def count_tagsIssues(filename):
    '''
    Iterate through the file count the number of issues mapped.
    Return a dictionary with the counting of each issue.
    '''
    keys = {"lower": 0, "lower_colon": 0, "problemchars": 0, "other": 0}
    for _, element in ET.iterparse(filename):
        keys = key_type(element, keys)
        element.clear() # discard the element

    return keys





def count_users(filename):
    '''
    Return a set of unique users
    '''
    users = set()
    for _, element in ET.iterparse(filename):
        users= get_user(element,users)
        element.clear() # discard the element

    return users





  
def betterStreetNames(filename):
    '''
    Return a dictionary with corrected street names.
    ''' 
    st_types = audit(filename)
    d_newName=defaultdict(str)
    for st_type, ways in st_types.iteritems():
        for name in ways:
            better_name = update_name_and_titles(name, mapping, mapping_title)
            d_newName[name.lower()]=better_name
            # if better_name:print name, "=>", better_name

    return d_newName


def process_map(file_in, pretty = False):
    '''
    Create a file with the OSM reshaped to be imported into mongoDB.
    Return None.
    '''
    global TRACK_STREETS, TRACK_CITIES
    TRACK_STREETS=0
    TRACK_CITIES=0   
    #create a dictionary with problematic street names
    d_streetName=betterStreetNames(file_in) 
    #Reshape the file and insert it in another file
    #when it is possible
    file_out = "{0}.json".format(file_in)
    #data = []
    i_num=0
    set_streets=set()
    with codecs.open(file_out, "w") as fo:
        for _, element in ET.iterparse(file_in ,events=("start",)):
            el = shape_element(element,d_streetName)
            if el:
                #track some information about the data
                i_num+=1
                if "address" in el:
                    if "street" in el['address']: 
                        set_streets.add(el['address']['street'])
                #print data
                if pretty:
                    fo.write(json.dumps(el, indent=2)+"\n")
                else:
                    fo.write(json.dumps(el) + "\n")
            element.clear() # discard the element
    s_txt="# of documents created: {}\n"
    s_txt+="# of different street names after corrections: {}\n"
    s_txt+="# of docs where the street name was fixed: {}\n"
    s_txt+="# of docs where the city name was fixed: {}\n"
    print s_txt.format(i_num, len(set_streets),TRACK_STREETS,TRACK_CITIES)




def count_streets_in_dbf(fr_dbf):
    '''
    Count the number unique street names, taking note of the city where it is located.
    **This function uses the dbf library that can be found here: 
    link: https://pypi.python.org/pypi/dbfpy/2.3.0
    It also explores the dataset from Center for metropolitan Studies of Sao Paulo.
    link: http://www.fflch.usp.br/centrodametropole/en/716
    '''
    #create an object to read the file
    db = dbf.Dbf(fr_dbf)
    street_set=set()
    #loop the file adding to a set a string formed by the street and city name.
    #It makes sure that the same street name in different cities is counted correctely.
    for rec in db:
        s_street=unicode(rec['NOME_ACEN'], 'latin1').title()
        s_city=rec['MUNICIPIO'].title()
        if (len(s_street)>1) & (len(s_city)):
            s_key="{} | {}".format(unidecode(s_street).lower(),s_city.lower())
            street_set.add(s_key)
    return street_set





def initial_tests(filename):
    '''
    Perform basic check on the data in the OSM file.
    '''
    #count tags
    d=count_tags(filename)
    print '# of tags:'
    pprint.pprint(d)
    print '\n'
    #count issues
    keys = count_tagsIssues(filename)
    print '# of potential problems on the data:'
    pprint.pprint(keys)
    print '\n'
    #count users
    users = count_users(filename)
    print '# of unique users that contributed to this map:\n {}'.format(len(users))
    print '\n'





