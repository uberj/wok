import os
from collections import namedtuple
from datetime import datetime

import jinja2
import yaml
import re
from pprint import pprint

from wok import util
from wok import renderers

class Page(object):
    """
    A single page on the website in all it's form, as well as it's
    associated metadata.
    """

    def __init__(self, path, options, renderer=None):
        """
        Load a file from disk, and parse the metadata from it.

        Note that you still need to call `render` and `write` to do anything
        interesting.
        """
        self.header = None
        self.original = None
        self.parsed = None
        self.options = options
        self.renderer = renderer if renderer else renderers.Plain

        # TODO: It's not good to make a new environment every time, but we if
        # we pass the options in each time, its possible it will change per
        # instance. Fix this.
        self.tmpl_env = jinja2.Environment(loader=jinja2.FileSystemLoader(
            self.options.get('template_dir', 'templates')))

        self.path = path
        _, self.filename = os.path.split(path)

        with open(path) as f:
            self.original = f.read()
            # Maximum of one split, so --- in the content doesn't get split.
            splits = self.original.split('---', 1)

            # Handle the case where no meta data was provided
            if len(splits) == 1:
                self.original = splits[0]
            else:
                header = splits[0]
                self.original = splits[1]
                self.meta = yaml.load(header)

        self.build_meta()
        util.out.info('Rendering {0} with {1}'.format(
            self.meta['slug'], self.renderer))
        self.meta['content'] = self.renderer.render(self.original)

    def build_meta(self):
        """
        Ensures the guarantees about metadata for documents are valid.

        `page.title` - will exist and will be a string.
        `page.slug` - will exist and will be a string.
        `page.author` - will exist, and contain fields `name` and `email`.
        `page.category` - will be a list.
        `page.published` - will exist.
        `page.datetime` - will be a datetime.
        `page.tags` - will be a list.
        `page.url` - will be the url of the page, relative to the wb root.
        `page.subpages` - will be a list containing every sub page of this page.
        """

        if self.meta is None:
            self.meta = {}

        # title
        if not 'title' in self.meta:
            self.meta['title'] = '.'.join(self.filename.split('.')[:-1])
            if (self.meta['title'] == ''):
                self.meta['title'] = self.filename

            util.out.warn("You didn't specify a title in {0}. "
                    "Using the file name as a title.".format(self.filename))

        # slug
        if not 'slug' in self.meta:
            self.meta['slug'] = util.slugify(self.meta['title'])
            util.out.debug("You didn't specify a slug, generating it from the title.")
        elif self.meta['slug'] != util.slugify(self.meta['slug']):
            util.out.warn('Your slug should probably be all lower case, and '
                'match "[a-z0-9-]*"')

        # author
        if 'author' in self.meta:
            self.meta['author'] = Author.parse(self.meta['author'])
        elif 'author' in self.options:
            self.meta['author'] = self.options['author']
        else:
            self.meta['author'] = Author()

        # category
        if 'category' in self.meta:
            self.meta['category'] = self.meta['category'].split('/')
        else:
            self.meta['category'] = []
        if self.meta['category'] == None:
            self.meta = []

        # published
        if not 'published' in self.meta:
            self.meta['published'] = True

        # datetime
        for name in ['time', 'date']:
            if name in self.meta:
                self.meta['datetime'] = self.meta[name]
        if not 'datetime' in self.meta:
            self.meta['datetime'] = datetime.now()

        # tags
        if not 'tags' in self.meta:
            self.meta['tags'] = []
        else:
            self.meta['tags'] = [t.strip() for t in
                    self.meta['tags'].split(',')]

        util.out.debug('Tags for {0}: {1}'.
                format(self.meta['slug'], self.meta['tags']))

        # url
        if not 'url' in self.meta:
            parts = {
                'slug' : self.meta['slug'],
                'category' : '/'.join(self.meta['category']),
                'page': '',
            }
            self.meta['url'] = self.options['url_pattern'].format(**parts);

        # subpages
        self.meta['subpages'] = []

    def render(self, templ_vars=None):
        """
        Renders the page to full html with the template engine.
        """
        type = self.meta.get('type', 'default')
        template = self.tmpl_env.get_template(type + '.html')

        if not templ_vars:
            templ_vars = {}

        if 'page' in templ_vars:
            util.out.debug('Found defaulted page data.')
            templ_vars['page'].update(self.meta)
        else:
            templ_vars['page'] = self.meta

        pagination = []
        cur_page = 0
        if 'paginate' in self.meta:
            # For now assume that it is page.subpages

            for chunk in util.chunk(templ_vars['page']['subpages'],
                    self.meta['paginatecount']):

                pagination.append({
                    'cur_page': cur_page+1,
                    'page_items': chunk,
                })
                cur_page += 1
        else:
            pagination = [{'cur_page': '', 'num_pages': '', 'page_items': []}]
            num_pages = 1


        util.out.debug(self.meta['title'])

        self.html = {}
        for page in pagination:
            page['num_pages'] = cur_page
            vars = templ_vars.copy();
            vars['pagination'] = page

            parts = {
                'slug' : self.meta['slug'],
                'category' : '/'.join(self.meta['category']),
                'page': page['cur_page'] if page['cur_page'] > 1 else '',
            }
            page_url = self.options['url_pattern'].format(**parts)
            page_url = re.sub(r'//+', '/', page_url)
            util.out.debug('parts: ' + repr(parts) + ' url: ' + page_url)

            if parts['page'] != '':
                prev_parts = parts.copy()
                if prev_parts['page'] == 2:
                    prev_parts['page'] = ''
                else:
                    prev_parts['page'] -= 1

                page['prev_url'] = self.options['url_pattern'].format(**prev_parts)
                page['prev_url'] = re.sub(r'//+', '/', page['prev_url'])

                util.out.debug('prev_parts: ' + repr(prev_parts) + ' prev: ' + page['prev_url'])

            if parts['page'] == '' or parts['page'] < page['num_pages']:
                next_parts = parts.copy()
                if next_parts['page'] == '':
                    next_parts['page'] = 2
                else:
                    next_parts['page'] += 1
                page['next_url'] = self.options['url_pattern'].format(**next_parts)
                page['next_url'] = re.sub(r'//+', '/', page['next_url'])
                util.out.debug('next_parts: ' + repr(next_parts) + ' next: ' + page['next_url'])


            self.html[page_url] = template.render(vars)

    def write(self):
        """Write the page to an html file on disk."""

        for url, page in self.html.items():
            # Use what we are passed, or the default given, or the current dir
            path = self.options.get('output_dir', '.')
            path += url

            try:
                os.makedirs(os.path.dirname(path))
            except OSError as e:
                util.out.debug('makedirs failed for {0}'.format(
                    os.path.basename(path)))
                # Probably that the dir already exists, so thats ok.
                # TODO: double check this. Permission errors are something to worry
                # about
            util.out.info('writing to {0}'.format(path))

            f = open(path, 'w')
            f.write(page)
            f.close()

    def __repr__(self):
        return "<wok.page.Page '{0}'>".format(self.meta['slug'])


class Author(object):
    """Smartly manages a author with name and email"""
    parse_author_regex = re.compile(r'^([^<>]*) *(<(.*@.*)>)?$')

    def __init__(self, raw='', name=None, email=None):
        self.raw = raw.strip()
        self.name = name
        self.email = email

    @classmethod
    def parse(cls, raw):
        a = cls(raw)
        a.name, _, a.email = cls.parse_author_regex.match(raw).groups()
        if a.name:
            a.name = a.name.strip()
        if a.email:
            a.email = a.email.strip()
        return a

    def __str__(self):
        if not self.name:
            return self.raw
        if not self.email:
            return self.name

        return "{0} <{1}>".format(self.name, self.email)

