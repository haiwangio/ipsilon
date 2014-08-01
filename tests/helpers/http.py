#!/usr/bin/python
#
# Copyright (C) 2014  Simo Sorce <simo@redhat.com>
#
# see file 'COPYING' for use and warranty information
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


from lxml import html
import requests
import string
import urlparse


class WrongPage(Exception):
    pass


class PageTree(object):

    def __init__(self, result):
        self.result = result
        self.text = result.text
        self._tree = None

    @property
    def tree(self):
        if self._tree is None:
            self._tree = html.fromstring(self.text)
        return self._tree

    def first_value(self, rule):
        result = self.tree.xpath(rule)
        if type(result) is list:
            if len(result) > 0:
                result = result[0]
            else:
                result = None
        return result

    def all_values(self, rule):
        result = self.tree.xpath(rule)
        if type(result) is list:
            return result
        return [result]

    def make_referer(self):
        return self.result.url

    def expected_value(self, rule, expected):
        value = self.first_value(rule)
        if value != expected:
            raise ValueError("Expected [%s], got [%s]" % (expected, value))


class HttpSessions(object):

    def __init__(self):
        self.servers = dict()

    def add_server(self, name, baseuri, user=None, pwd=None):
        new = {'baseuri': baseuri,
               'session': requests.Session()}
        if user:
            new['user'] = user
        if pwd:
            new['pwd'] = pwd
        self.servers[name] = new

    def get_session(self, url):
        for srv in self.servers:
            d = self.servers[srv]
            if url.startswith(d['baseuri']):
                return d['session']

        raise ValueError("Unknown URL: %s" % url)

    def get(self, url, **kwargs):
        session = self.get_session(url)
        return session.get(url, allow_redirects=False, **kwargs)

    def post(self, url, **kwargs):
        session = self.get_session(url)
        return session.post(url, allow_redirects=False, **kwargs)

    def access(self, action, url, **kwargs):
        action = string.lower(action)
        if action == 'get':
            return self.get(url, **kwargs)
        elif action == 'post':
            return self.post(url, **kwargs)
        else:
            raise ValueError("Unknown action type: [%s]" % action)

    def new_url(self, referer, action):
        if action.startswith('/'):
            u = urlparse.urlparse(referer)
            return '%s://%s%s' % (u.scheme, u.netloc, action)
        return action

    def get_form_data(self, page, form_id, input_fields):
        values = []
        action = page.first_value('//form[@id="%s"]/@action' % form_id)
        values.append(action)
        method = page.first_value('//form[@id="%s"]/@method' % form_id)
        values.append(method)
        for field in input_fields:
            value = page.all_values('//form[@id="%s"]/input/@%s' % (form_id,
                                                                    field))
            values.append(value)
        return values

    def handle_login_form(self, idp, page):
        if type(page) != PageTree:
            raise TypeError("Expected PageTree object")

        srv = self.servers[idp]

        try:
            results = self.get_form_data(page, "login_form", ["name", "value"])
            action_url = results[0]
            method = results[1]
            names = results[2]
            values = results[3]
            if action_url is None:
                raise Exception
        except Exception:  # pylint: disable=broad-except
            raise WrongPage("Not a Login Form Page")

        referer = page.make_referer()
        headers = {'referer': referer}
        payload = {}
        for i in range(0, len(names)):
            payload[names[i]] = values[i]

        # replace known values
        payload['login_name'] = srv['user']
        payload['login_password'] = srv['pwd']

        return [method, self.new_url(referer, action_url),
                {'headers': headers, 'data': payload}]

    def handle_return_form(self, page):
        if type(page) != PageTree:
            raise TypeError("Expected PageTree object")

        try:
            results = self.get_form_data(page, "saml-response",
                                         ["name", "value"])
            action_url = results[0]
            if action_url is None:
                raise Exception
            method = results[1]
            names = results[2]
            values = results[3]
        except Exception:  # pylint: disable=broad-except
            raise WrongPage("Not a Return Form Page")

        referer = page.make_referer()
        headers = {'referer': referer}

        payload = {}
        for i in range(0, len(names)):
            payload[names[i]] = values[i]

        return [method, self.new_url(referer, action_url),
                {'headers': headers, 'data': payload}]

    def fetch_page(self, idp, target_url):
        url = target_url
        action = 'get'
        args = {}

        while True:
            r = self.access(action, url, **args)  # pylint: disable=star-args
            if r.status_code == 303:
                url = r.headers['location']
                action = 'get'
                args = {}
            elif r.status_code == 200:
                page = PageTree(r)

                try:
                    (action, url, args) = self.handle_login_form(idp, page)
                    continue
                except WrongPage:
                    pass

                try:
                    (action, url, args) = self.handle_return_form(page)
                    continue
                except WrongPage:
                    pass

                # Either we got what we wanted, or we have to stop anyway
                return page
            else:
                raise ValueError("Unhandled status (%d) on url %s" % (
                                 r.status_code, url))

    def auth_to_idp(self, idp):

        srv = self.servers[idp]
        target_url = '%s/%s/' % (srv['baseuri'], idp)

        r = self.access('get', target_url)
        if r.status_code != 200:
            raise ValueError("Access to idp failed: %s" % repr(r))

        page = PageTree(r)
        page.expected_value('//div[@id="content"]/p/a/text()', 'Log In')
        href = page.first_value('//div[@id="content"]/p/a/@href')
        url = self.new_url(target_url, href)

        page = self.fetch_page(idp, url)
        page.expected_value('//div[@id="welcome"]/p/text()',
                            'Welcome %s!' % srv['user'])

    def add_sp_metadata(self, idp, sp):
        idpsrv = self.servers[idp]
        idpuri = idpsrv['baseuri']
        spuri = self.servers[sp]['baseuri']

        url = '%s/%s/admin/providers/saml2/admin/new' % (idpuri, idp)
        headers = {'referer': url}
        payload = {'name': sp}
        m = requests.get('%s/saml2/metadata' % spuri)
        metafile = {'metafile': m.content}
        r = idpsrv['session'].post(url, headers=headers,
                                   data=payload, files=metafile)
        if r.status_code != 200:
            raise ValueError('Failed to post SP data [%s]' % repr(r))

        page = PageTree(r)
        page.expected_value('//div[@class="alert alert-success"]/p/text()',
                            'SP Successfully added')