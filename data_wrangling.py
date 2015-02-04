#!/usr/bin/python
# -*- coding: utf-8 -*-
'''
Clean and reshape data from Open Street maps and
insert explore it in mongo DB.  

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
u'ibi\xfana-sp': u"Ibiúna" 
}

# variables to create docs to Mongo
CREATED = [ "version", "changeset", "timestamp", "user", "uid"]
NODE = ["id","visible","amenity","cuisine","name","phone"]




'''
Begin of Help Functions
'''


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


def shape_element(element,d_streetName,d_wrongCitiesNames=d_wrongCitiesNames):
    '''

    Street and City names are required
    '''
    node={}
    if element.tag == "node" or element.tag == "way" :
        if element.tag == 'node':
            node['type'] = 'node'
        else:
            node['type'] = 'way'
            for tag in element.iter("tag"):
                #check problemns
                s = tag.attrib['k']
                if s.count(":")>1: continue
                if problemchars.search(s): continue 
                #set the name to be insert in the dict
                better_name=tag.attrib['v']                
                #check k type
                if s[:5]=='addr:':
                    #initialize address dict in node dict
                    if 'address' not in node: node['address']={}
                    #if is needed, correct better_name
                    #if it was a city or a street name and there is 
                    #no valid string for it, return None
                    if  is_street_name(elem):
                        if tag.attrib['v'] in  d_streetName:
                            better_name=d_streetName[better_name]
                            if not better_name: return None
                    elif is_city_name(element):
                        if not better_name: return None
                        if tag.attrib['v'] in  d_wrongCitiesNames:
                            better_name=d_wrongCitiesNames[better_name] 
                    #set the address node                     
                    node['address'][s[5:]]=better_name
                else:
                    node[s]=better_name
    
            for tag in element.iter("nd"):
                if 'node_refs' not in node: node['node_refs']=[]
                node['node_refs'].append(tag.attrib['ref'])

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



def process_map(file_in, pretty = False):
    '''
    '''   
    #create a dictionary with problematic street names
    d_streetName=betterStreetNames(file_in) 
    #Reshape the file and insert it in another file
    #when it is possible
    file_out = "{0}.json".format(file_in)
    #data = []
    with codecs.open(file_out, "w") as fo:
        for _, element in ET.iterparse(file_in):
            el = shape_element(element,d_streetName)
            if el:
                #data.append(el)
                if pretty:
                    fo.write(json.dumps(el, indent=2)+"\n")
                else:
                    fo.write(json.dumps(el) + "\n")
            elem.clear() # discard the element
    #return data





def initial_tests(filename):
	'''
	...
	'''
	#count tags
	d=count_tags(filename)
	pprint.pprint(d)
	#count issues
	keys = count_tagsIssues(filename)
	pprint.pprint(keys)
	#count users
	users = count_users(filename)
	print 'Unique Users that contributed to this map: {}'.format(len(users))



