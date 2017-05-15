#!/usr/bin/python
#
# Copyright (C) 2015 Ipsilon project Contributors, for license see COPYING

from __future__ import print_function

from helpers.common import IpsilonTestBase  # pylint: disable=relative-import
from helpers.http import HttpSessions  # pylint: disable=relative-import
import os
import sys
from string import Template


idp_g = {'TEMPLATES': '${TESTDIR}/templates/install',
         'CONFDIR': '${TESTDIR}/etc',
         'DATADIR': '${TESTDIR}/lib',
         'CACHEDIR': '${TESTDIR}/cache',
         'HTTPDCONFD': '${TESTDIR}/${NAME}/conf.d',
         'STATICDIR': '${ROOTDIR}',
         'BINDIR': '${ROOTDIR}/ipsilon',
         'WSGI_SOCKET_PREFIX': '${TESTDIR}/${NAME}/logs/wsgi'}


idp_a = {'hostname': '${ADDRESS}:${PORT}',
         'admin_user': 'tuser',
         'system_user': '${TEST_USER}',
         'instance': '${NAME}',
         'pam': 'no',
         'gssapi': 'no',
         'ipa': 'no',
         'ldap': 'yes',
         'ldap_server_url': 'ldap://${ADDRESS}:45389/',
         'ldap_bind_dn_template':
         'uid=%(username)s,ou=People,dc=example,dc=com',
         'ldap_tls_level': 'NoTLS',
         'server_debugging': 'True'}


sp_g = {'HTTPDCONFD': '${TESTDIR}/${NAME}/conf.d',
        'SAML2_TEMPLATE': '${TESTDIR}/templates/install/saml2/sp.conf',
        'CONFFILE': '${TESTDIR}/${NAME}/conf.d/ipsilon-%s.conf',
        'HTTPDIR': '${TESTDIR}/${NAME}/%s'}


sp_a = {'hostname': '${ADDRESS}',
        'saml_idp_metadata': 'https://127.0.0.10:45080/idp1/saml2/metadata',
        'saml_auth': '/sp',
        'httpd_user': '${TEST_USER}'}


def fixup_sp_httpd(httpdir):
    merge = """
    MellonSetEnv "GROUPS" "groups"
    MellonMergeEnvVars On
</Location>"""
    with open(httpdir + '/conf.d/ipsilon-saml.conf', 'r') as f:
        conf = f.read()
    conf = conf.replace('</Location>', merge, 1)
    with open(httpdir + '/conf.d/ipsilon-saml.conf', 'w') as f:
        f.write(conf)

    location = """

Alias /sp ${HTTPDIR}/sp

<Directory ${HTTPDIR}/sp>
    <IfModule mod_authz_core.c>
        Require all granted
    </IfModule>
    <IfModule !mod_authz_core.c>
        Order Allow,Deny
        Allow from All
    </IfModule>
    Options +Includes
</Directory>
"""
    t = Template(location)
    text = t.substitute({'HTTPDIR': httpdir})
    with open(httpdir + '/conf.d/ipsilon-saml.conf', 'a') as f:
        f.write(text)

    index = """<!--#echo var="MELLON_GROUPS" -->"""
    os.mkdir(httpdir + '/sp')
    with open(httpdir + '/sp/index.shtml', 'w') as f:
        f.write(index)


class IpsilonTest(IpsilonTestBase):

    def __init__(self):
        super(IpsilonTest, self).__init__('ldap', __file__)

    def setup_servers(self, env=None):

        print("Installing IDP's ldap server")
        addr = '127.0.0.10'
        port = '45389'
        conf = self.setup_ldap(env)

        print("Starting IDP's ldap server")
        self.start_ldap_server(conf, addr, port, env)

        print("Installing IDP server")
        name = 'idp1'
        addr = '127.0.0.10'
        port = '45080'
        idp = self.generate_profile(idp_g, idp_a, name, addr, port)
        conf = self.setup_idp_server(idp, name, addr, port, env)

        print("Starting IDP's httpd server")
        self.start_http_server(conf, env)

        print("Installing SP server")
        name = 'sp1'
        addr = '127.0.0.11'
        port = '45081'
        sp = self.generate_profile(sp_g, sp_a, name, addr, port)
        conf = self.setup_sp_server(sp, name, addr, port, env)
        fixup_sp_httpd(os.path.dirname(conf))

        print("Starting SP's httpd server")
        self.start_http_server(conf, env)


if __name__ == '__main__':

    idpname = 'idp1'
    spname = 'sp1'
    user = 'tuser'

    sess = HttpSessions()
    sess.add_server(idpname, 'https://127.0.0.10:45080', user, 'tuser')
    sess.add_server(spname, 'https://127.0.0.11:45081')

    print("ldap: Authenticate to IDP ...", end=' ')
    try:
        sess.auth_to_idp(idpname)
    except Exception as e:  # pylint: disable=broad-except
        print(" ERROR: %s" % repr(e), file=sys.stderr)
        sys.exit(1)
    print(" SUCCESS")

    print("ldap: Add SP Metadata to IDP ...", end=' ')
    try:
        sess.add_sp_metadata(idpname, spname)
    except Exception as e:  # pylint: disable=broad-except
        print(" ERROR: %s" % repr(e), file=sys.stderr)
        sys.exit(1)
    print(" SUCCESS")

    print("ldap: Access SP Protected Area ...", end=' ')
    try:
        page = sess.fetch_page(idpname,
                               'https://127.0.0.11:45081/sp/index.shtml')
        page.expected_value('text()', 'Test Group;Test Group 2')
    except ValueError as e:
        print(" ERROR: %s" % repr(e), file=sys.stderr)
        sys.exit(1)
    print(" SUCCESS")
