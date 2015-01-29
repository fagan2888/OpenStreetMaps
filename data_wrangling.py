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




#define some regular expressions checks
lower = re.compile(r'^([a-z]|_)*$')
lower_colon = re.compile(r'^([a-z]|_)*:([a-z]|_)*$')
problemchars = re.compile(r'[=\+/&<>;\'"\?%#$@\,\. \t\r\n]')
problemchars2 = re.compile(r'[=\+/&<>;\'"\?%#$@\,\ \t\r\n]')
street_type_re = re.compile(r'([^\s]+)', re.IGNORECASE)




expected =['avenida',"alameda",'largo','travessa',u'praça', 'via','viaduto','viela', 'estrada', 'rodovia', 'rua','passagem']

# UPDATE THIS VARIABLE
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


















def audit_street_type(street_types, street_name):
    m = street_type_re.search(street_name)
    if m:
        street_type = m.group().lower()
        if street_type not in expected:
            street_types[street_type].add(street_name)
            
def audit_street_type_new(street_types, street_name):
    m = street_type_re.search(street_name)
    if m:
        street_type = m.group().lower()
        if street_type not in expected:
            street_types[street_type].add(street_name)
        #check the second word, when it exists
        l_names=street_name.split()
        if len(l_names)>1:
            s=l_names[1].lower()
            if '.' == s[-1]: s = s[:-1]
            if s in mapping_title:
                 street_types[street_type].add(street_name)
            

def is_street_name(elem):
    return (((elem.attrib['k']).lower() == "addr:street") )


def audit(osmfile):
    osm_file = open(osmfile, "r")
    street_types = defaultdict(set)
    for event, elem in ET.iterparse(osm_file, events=("start",)):

        if elem.tag == "node" or elem.tag == "way":
            for tag in elem.iter("tag"):
                if is_street_name(tag):
                    audit_street_type_new(street_types, tag.attrib['v'])
            elem.clear() # discard the element

    return street_types




def update_name(name, mapping):
    s=name.split()[0].lower()
    name=name[len(s):len(name)].lower().strip()
    if '.' in s[-1]: s = s[:-1]
    if s not in mapping: return None
    name=(u"{} {}".format(mapping[s],name)).title() 
    return name

def update_name_new(name, mapping):
    s=name.split()[0].lower()
    name=name[len(s):len(name)].lower().strip()
    if '.' in s[-1]: s = s[:-1]
    if s not in mapping: return None
    if problemchars2.search(name):
        l=[x for x in problemchars2.findall(name) if x !=' ']
        if l: name=name.split(l[0])[0]
    try:
        name=(u"{} {}".format(mapping[s],unicode(name.strip(), 'utf8'))).title() 
    except UnicodeDecodeError :
        name=(u"{} {}".format(mapping[s],unicode(name.strip(), 'latin1'))).title()
    except TypeError:
        name=(u"{} {}".format(mapping[s],name.strip())).title()         
    return name


def update_name_and_titles(name, mapping, mapping_title):
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



