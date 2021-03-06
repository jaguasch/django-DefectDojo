'''
Faraday Penetration Test IDE
Copyright (C) 2013  Infobyte LLC (http://www.infobytesec.com/)
See the file 'doc/LICENSE' for the license information

'''
from __future__ import with_statement

from defusedxml import ElementTree as ET

import html2text

from dojo.models import Endpoint, Finding

__author__ = "Micaela Ranea Sanchez"
__copyright__ = "Copyright (c) 2013, Infobyte LLC"
__credits__ = ["Francisco Amato", "Federico Kirschbaum", "Micaela Ranea Sanchez", "German Riera"]
__license__ = ""
__version__ = "1.0.0"
__maintainer__ = "Micaela Ranea Sanchez"
__email__ = "mranea@infobytesec.com"
__status__ = "Development"


class NexposeFullXmlParser(object):
    """
    The objective of this class is to parse Nexpose's XML 2.0 Report.

    TODO: Handle errors.
    TODO: Test nexpose output version. Handle what happens if the parser doesn't support it.
    TODO: Test cases.

    @param xml_filepath A proper xml generated by nexpose
    """

    def __init__(self, xml_output, test):
        tree = self.parse_xml(xml_output)

        vulns = []
        if tree:
            vulns = self.get_vuln_definitions(tree)
            self.items = self.get_items(tree, vulns, test)
        else:
            self.items = []
        self.tree = tree
        self.vulns = vulns

    def parse_xml(self, xml_output):
        """
        Open and parse an xml file.

        TODO: Write custom parser to just read the nodes that we need instead of
        reading the whole file.

        @return xml_tree An xml tree instance. None if error.
        """
        try:
            tree = ET.parse(xml_output)
        except SyntaxError as se:
            raise se

        return tree

    def parse_html_type(self, node):
        """
        Parse XML element of type HtmlType

        @return ret A string containing the parsed element
        """
        ret = ""
        tag = node.tag.lower()

        if tag == 'containerblockelement':

            if len(list(node)) > 0:
                for child in list(node):
                    ret += self.parse_html_type(child)
            else:
                if node.text:
                    ret += "<div>" + str(node.text).strip()
                if node.tail:
                    ret += str(node.tail).strip() + "</div>"
                else:
                    ret += "</div>"
        if tag == 'listitem':
            if len(list(node)) > 0:
                for child in list(node):
                    ret += self.parse_html_type(child)
            else:
                if node.text:
                    ret += "<li>" + str(node.text).strip() + "</li>"
        if tag == 'orderedlist':
            i = 1
            for item in list(node):
                ret += "<ol>" + str(i) + " " + self.parse_html_type(item) + "</ol>"
                i += 1
        if tag == 'paragraph':
            if len(list(node)) > 0:
                for child in list(node):
                    ret += self.parse_html_type(child)
            else:
                if node.text:
                    ret += "<p>" + node.text.encode('utf-8').strip()
                if node.tail:
                    ret += str(node.tail).strip() + "</p>"
                else:
                    ret += "</p>"
        if tag == 'unorderedlist':
            for item in list(node):
                unorderedlist = self.parse_html_type(item)
                if unorderedlist not in ret:
                    ret += "* " + unorderedlist
        if tag == 'urllink':
            if node.text:
                ret += str(node.text).strip() + " "
            last = ""

            for attr in node.attrib:
                if last != "":
                    if node.get(attr) != node.get(last):
                        ret += str(node.get(attr)) + " "
                last = attr

        return ret

    def parse_tests_type(self, node, vulnsDefinitions):
        """
        Parse XML element of type TestsType

        @return vulns A list of vulnerabilities according to vulnsDefinitions
        """
        vulns = list()

        for tests in node.iter('tests'):
            for test in tests.iter('test'):
                vuln = dict()
                if test.get('id').lower() in vulnsDefinitions:
                    vuln = vulnsDefinitions[test.get('id').lower()]
                    for desc in list(test):
                        if 'pluginOutput' in vuln:
                            vuln['pluginOutput'] += "\n\n" + self.parse_html_type(desc)
                        else:
                            vuln['pluginOutput'] = self.parse_html_type(desc)
                    vulns.append(vuln)

        return vulns

    def get_vuln_definitions(self, tree):
        """
        @returns vulns A dict of Vulnerability Definitions
        """
        vulns = dict()

        for vulnsDef in tree.iter('VulnerabilityDefinitions'):
            for vulnDef in vulnsDef.iter('vulnerability'):
                vid = vulnDef.get('id').lower()
                vector = vulnDef.get('cvssVector')

                vuln = {
                    'desc': "",
                    'name': vulnDef.get('title'),
                    'refs': ["vector: " + vector, vid],
                    'resolution': "",
                    'severity': (int(vulnDef.get('severity')) - 1) / 2,
                    'tags': list()
                }

                for item in list(vulnDef):
                    if item.tag == 'description':
                        for htmlType in list(item):
                            vuln['desc'] += self.parse_html_type(htmlType)

                    if item.tag == 'exploits':
                        for exploit in list(item):
                            vuln['refs'].append(
                                    str(exploit.get('title')).strip() + ' ' + str(exploit.get('link')).strip())
                    if item.tag == 'references':
                        for ref in list(item):
                            vuln['refs'].append(str(ref.text).strip())
                    if item.tag == 'solution':
                        for htmlType in list(item):
                            vuln['resolution'] += self.parse_html_type(htmlType)
                    """
                    # there is currently no method to register tags in vulns
                    if item.tag == 'tags':
                        for tag in list(item):
                            vuln['tags'].append(tag.text.lower())
                    """
                vulns[vid] = vuln
        return vulns

    def get_items(self, tree, vulns, test):
        """
        @return hosts A list of Host instances
        """

        x = list()
        if tree is None:
            return x
        for nodes in tree.iter('nodes'):
            "in nodes"
            for node in nodes.iter('node'):
                host = dict()
                host['name'] = node.get('address')
                host['hostnames'] = set()
                host['os'] = ""
                host['services'] = list()
                # host['vulns'] = self.parse_tests_type(node, vulns)

                for names in node.iter('names'):
                    for name in list(names):
                        host['hostnames'].add(name.text)

                for endpoints in node.iter('endpoints'):
                    for endpoint in list(endpoints):
                        svc = {
                            'protocol': endpoint.get('protocol'),
                            'port': endpoint.get('port'),
                            'status': endpoint.get('status'),
                        }
                        for services in endpoint.iter('services'):
                            for service in list(services):
                                svc['name'] = service.get('name')
                                svc['vulns'] = self.parse_tests_type(service, vulns)

                                for configs in service.iter('configurations'):
                                    for config in list(configs):
                                        if "banner" in config.get('name'):
                                            svc['version'] = config.get('name')

                        host['services'].append(svc)

                x.append(host)

        dupes = {}

        for item in x:
            for service in item['services']:
                for vuln in service['vulns']:
                    for sev, num_sev in Finding.SEVERITIES.iteritems():
                        if num_sev == vuln['severity']:
                            break

                    dupe_key = sev + vuln['name']

                    if dupe_key in dupes:
                        find = dupes[dupe_key]
                        dupe_text = html2text.html2text(vuln['pluginOutput'].decode("utf8"))
                        if dupe_text not in find.description:
                            find.description += "\n\n" + dupe_text
                    else:
                        refs = ''
                        for ref in vuln['refs'][2:]:
                            if ref.startswith('CA'):
                                ref = "https://www.cert.org/advisories/" + ref + ".html"
                            elif ref.startswith('CVE'):
                                ref = "https://cve.mitre.org/cgi-bin/cvename.cgi?name=" + ref
                            refs += ref
                            refs += "\n"
                        find = Finding(title=vuln['name'],
                                       description=html2text.html2text(
                                               vuln['desc'].encode('utf-8').strip()) + "\n\n" + html2text.html2text(vuln['pluginOutput'].decode("utf8").strip()),
                                       severity=sev,
                                       numerical_severity=Finding.get_numerical_severity(sev),
                                       mitigation=html2text.html2text(vuln['resolution']),
                                       impact=vuln['refs'][0],
                                       references=refs,
                                       test=test,
                                       active=False,
                                       verified=False,
                                       false_p=False,
                                       duplicate=False,
                                       out_of_scope=False,
                                       mitigated=None,
                                       dynamic_finding=True)
                        find.unsaved_endpoints = list()
                        dupes[dupe_key] = find

                    find.unsaved_endpoints.append(Endpoint(host=item['name'], product=test.engagement.product))
                    for hostname in item['hostnames']:
                        find.unsaved_endpoints.append(Endpoint(host=hostname, product=test.engagement.product))
                    for service in item['services']:
                        if len(service['vulns']) > 0:
                            find.unsaved_endpoints.append(
                                    Endpoint(host=item['name'] + (":" + service['port']) if service[
                                                                                                'port'] is not None else "",
                                             product=test.engagement.product))

        return dupes.values()
