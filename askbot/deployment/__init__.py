"""
module for deploying askbot
"""

import os.path
import sys
from collections import OrderedDict
from optparse import OptionParser
from argparse import ArgumentParser
from askbot.deployment import messages
from askbot.deployment.messages import print_message
from askbot.deployment import path_utils
from askbot.utils import console
from askbot.utils.functions import generate_random_key
from askbot.deployment.template_loader import DeploymentTemplate
from askbot.deployment.parameters import ConfigManagerCollection

import shutil

DATABASE_ENGINE_CHOICES = ('1', '2', '3', '4')

class AskbotSetup:

    PROJECT_FILES_TO_CREATE = set(('manage.py',))
    APP_FILES_TO_CREATE     = set(path_utils.FILES_TO_CREATE) - set(('manage.py',))
    SOURCE_DIR              = os.path.dirname(os.path.dirname(__file__)) # a.k.a. ASKBOT_ROOT in settings.py

    def __init__(self, interactive=True, verbosity=-128):
        self.parser = ArgumentParser(description="Setup a Django project and app for Askbot")
        self.verbosity = verbosity
        self._todo = {}
        self.configManagers = ConfigManagerCollection(interactive=interactive, verbosity=verbosity)
        self._add_arguments()

    def _add_arguments(self):
        self._add_setup_args()
        self._add_settings_args()
        self._add_db_args()
        self._add_cache_args()


    def _add_settings_args(self):
        """Misc parameters for rendering settings.py
        Adds
        --logfile-name
        --append-settings
        --no-secret-key
        """

        self.parser.add_argument(
            "--logfile-name",
            dest="logfile_name",
            default='askbot.log',
            help="name of the askbot logfile."
        )

        self.parser.add_argument(
            "--append-settings",
            dest="local_settings",
            default='',
            help="Extra settings file to append custom settings"
        )

        self.parser.add_argument(
            "--no-secret-key",
            dest="no_secret_key",
            action='store_true',
            help="Don't generate a secret key. (not recommended)"
        )

    def _add_setup_args(self):
        """Control the behaviour of this setup procedure
        Adds
        --create - project
        --dir-name, -n
        --verbose, -v
        --force
        --dry-run
        --use-defaults
        """

        self.parser.add_argument(
            '--create-project',
            dest='create_project',
            action='store',
            default='django',
            help='Deploy a new Django project (default)'
        )

        self.parser.add_argument(
            "--dir-name", "-n",
            dest = "dir_name",
            default = '',
            help = "Directory where you want to install the Django project."
        )

        self.parser.add_argument(
            "--app-name",
            dest="app_name",
            default='askbot_app',
            help="Django app name (subdir) for this Askbot deployment in the target Django project."
        )

        self.parser.add_argument(
            "--verbose", "-v",
            dest = "verbosity",
            default = 1,
            type=int,
            choices=[0,1,2],
            help = "verbosity level with 0 being the lowest"
        )

        self.parser.add_argument(
            "--force",
            dest="force",
            action='store_true',
            help="Force overwrite settings.py file"
        )

        self.parser.add_argument(
            "--dry-run",
            dest = "dry_run",
            action='store_true',
            help="Dump parameters and do not install askbot after input validation."
        )

        self.parser.add_argument(
            "--use-defaults",
            dest="use_defaults",
            action='store_true',
            help="Use Askbot defaults where applicable. Defaults will be overwritten by commandline arguments."
        )

        self.parser.add_argument(
            "--no-input",
            dest="interactive",
            action='store_false',
            help="The installer will fail instead of asking for missing values."
        )

    def _add_cache_args(self):
        """Cache settings
        Adds
        --cache-engine
        --cache-node
        --cache-db
        --cache-password
        """
        engines = self.configManagers.configManager('cache').configField('cache_engine').cache_engines
        engine_choices = [e[0] for e in engines]
        self.parser.add_argument('--cache-engine',
            dest='cache_engine',
            action='store',
            default=None,
            type=int,
            choices=engine_choices,
            help='Select which Django cache backend to use.'
        )

        self.parser.add_argument('--cache-node',
            dest='cache_nodes',
            action='append',
            help='Add cache node to list of nodes. Specify node as <ip-address>:<port>. Can be provided multiple times.'
        )

        # only used by redis at the moment
        self.parser.add_argument('--cache-db',
            dest='cache_db',
            action='store',
            default=1,
            type=int,
            help='The name of the cache DB to use.'
        )

        # only used by redis at the moment
        self.parser.add_argument('--cache-password',
            dest='cache_password',
            action='store',
            help='The password to connect to the cache.'
        )

    def _add_db_args(self):
        """How to connect to the database
        Adds
        --db-engine,   -e
        --db-name,     -d
        --db-user",    -u
        --db-password, -p
        --db-host
        --db-port
        """
        engines = self.configManagers.configManager('database').configField('database_engine').database_engines
        engine_choices = [e[0] for e in engines]
        self.parser.add_argument(
            '--db-engine', '-e',
            dest='database_engine',
            action='store',
            choices=engine_choices,
            default=None,
            type=int,
            help='Database engine, type 1 for PostgreSQL, 2 for SQLite, 3 for MySQL, 4 for Oracle'
        )

        self.parser.add_argument(
            "--db-name", "-d",
            dest = "database_name",
            default = None,
            help = "The database name Askbot will use"
        )

        self.parser.add_argument(
            "--db-user", "-u",
            dest = "database_user",
            default = None,
            help = "The username Askbot uses to connect to the database"
        )

        self.parser.add_argument(
            "--db-password", "-p",
            dest = "database_password",
            default = None,
            help = "The password Askbot uses to connect to the database"
        )

        self.parser.add_argument(
            "--db-host",
            dest = "database_host",
            default = None,
            help = "The database host"
        )

        self.parser.add_argument(
            "--db-port",
            dest = "database_port",
            default = None,
            type=int,
            help = "The database port"
        )

    def _set_verbosity(self, options):
        self.verbosity = options.verbosity

    # I think this logic can be immediately attached to argparse
    # it would be a hack though
    def _set_create_project(self, options):
        # Currently the --create-project option only changes the installer's
        # behaviour if one passes "container-uwsgi" as argument
        todo = [ 'django' ] # This is the default as Askbot has always worked
        wish = str.lower(options.create_project)
        if wish in [ 'no', 'none', 'false', '0']:
            todo = [ 'nothing' ]
        elif wish == 'container-uwsgi':
            todo.append(wish)
        self._todo['create_project'] = todo

    def __call__(self): # this is the main part of the original askbot_setup()
      try:
        options = self.parser.parse_args()
        self._set_verbosity(options)
        self._set_create_project(options)
        print_message(messages.DEPLOY_PREAMBLE, self.verbosity)

        # the destination directory
        directory = path_utils.clean_directory(options.dir_name)
        while directory is None:
            directory = path_utils.get_install_directory(force=options.force) # i.e. ask the user
        options.dir_name = directory

        if options.database_engine not in DATABASE_ENGINE_CHOICES:
            options.database_engine = console.choice_dialog(
                'Please select database engine:\n1 - for postgresql, '
                '2 - for sqlite, 3 - for mysql, 4 - oracle',
                choices=DATABASE_ENGINE_CHOICES
            )

        options_dict = vars(options)

        from copy import deepcopy
        options_dict_2 = deepcopy(options_dict)

        if options.force is False:
            options_dict = collect_missing_options(options_dict)

        database_engine_codes = {
            '1': 'postgresql_psycopg2',
            '2': 'sqlite3',
            '3': 'mysql',
            '4': 'oracle'
        }
        database_engine = database_engine_codes[options.database_engine]
        options_dict['database_engine'] = database_engine

        if options_dict['dry_run']:

            self.configManagers.complete(options_dict_2)
            from pprint import pprint
            pprint(options_dict)
            pprint(options_dict_2)
            pprint(self.__dict__)
            raise KeyboardInterrupt

        self.deploy_askbot(options_dict)

        if database_engine == 'postgresql_psycopg2':
            try:
                import psycopg2
            except ImportError:
                print('\nNEXT STEPS: install python binding for postgresql')
                print('pip install psycopg2\n')
        elif database_engine == 'mysql':
            try:
                import _mysql
            except ImportError:
                print('\nNEXT STEP: install python binding for mysql')
                print('pip install mysql-python\n')

      except KeyboardInterrupt:
        print("\n\nAborted.")
        sys.exit(1)
        pass

    def _install_copy(self, copy_list, forced_overwrite=[], skip_silently=[]):
        print_message('Copying files:', self.verbosity)
        for src,dst in copy_list:
            print_message(f'* to {dst} from {src}', self.verbosity)
            if not os.path.exists(dst):
                shutil.copy(src, dst)
                continue
            matches = [ dst for c in forced_overwrite
                            if dst.endswith(f'{os.path.sep}{c}') ]
            if len(matches) > 0:
                print_message('  ^^^ forced overwrite!', self.verbosity)
                shutil.copy(src, dst)
            elif dst.split(os.path.sep)[-1] not in skip_silently:
                print_message(f'  ^^^ you already have one, please add contents of {src}', self.verbosity)
        print_message('Done.', self.verbosity)

    def _install_render_with_jinja2(self, render_list, context):
        print_message('Rendering files:', self.verbosity)
        template = DeploymentTemplate('dummy.name') # we use this a little differently than originally intended
        for src, dst in render_list:
            if os.path.exists(dst):
                print_message(f'* you already have a file "{dst}" please merge the contents', self.verbosity)
                continue
            print_message(f'*    {dst} from {src}', self.verbosity)
            template.tmpl_path = src
            output = template.render(context)
            with open(dst, 'w+') as output_file:
                output_file.write(output)
        print_message('Done.', self.verbosity)

    def _create_new_django_project(self, install_dir, options):
        log_dir  = os.path.join(install_dir, path_utils.LOG_DIR_NAME)
        log_file = os.path.join(log_dir, options['logfile_name'])

        create_me = [ install_dir, log_dir ]
        copy_me   = list()

        if 'django' in self._todo.get('create_project',[]):
            src = lambda x:os.path.join(self.SOURCE_DIR, 'setup_templates', x)
            dst = lambda x:os.path.join(install_dir, x)
            copy_me.extend([
               ( src(file_name), dst(file_name) )
               for file_name in self.PROJECT_FILES_TO_CREATE
            ])

        for d in create_me:
            path_utils.create_path(d)

        path_utils.touch(log_file)
        self._install_copy(copy_me, skip_silently=path_utils.BLANK_FILES)

    def _create_new_django_app(self, app_name, options):
        options['askbot_site'] = options['dir_name']
        options['askbot_app']  = app_name
        app_dir =  os.path.join(options['dir_name'], app_name)

        create_me = [ app_dir ]
        copy_me   = list()
        render_me = list()

        if 'django' in self._todo.get('create_project',[]):
            src = lambda x:os.path.join(self.SOURCE_DIR, 'setup_templates', x)
            dst = lambda x:os.path.join(app_dir, x)
            copy_me.extend([
                ( src(file_name), dst(file_name) )
                for file_name in self.APP_FILES_TO_CREATE
                ])
            render_me.extend([
                ( src('settings.py.jinja2'), dst('settings.py') )
                ])

        if 'container-uwsgi' in self._todo.get('create_project',[]):
            src = lambda x:os.path.join(self.SOURCE_DIR, 'container', x)
            dst = lambda x:os.path.join(app_dir, x)
            copy_me.extend([
                ( src(file_name), dst(file_name) )
                for file_name in [ 'cron-askbot.sh', 'prestart.sh', 'prestart.py' ]
            ])
            render_me.extend([
                ( src(file_name), dst(file_name) )
                for file_name in [ 'crontab', 'uwsgi.ini' ]
            ])

        for d in create_me:
            path_utils.create_path(d)

        self._install_copy(copy_me, skip_silently=path_utils.BLANK_FILES,
                                    forced_overwrite=['urls.py'])

        self._install_render_with_jinja2(render_me, options)

        if len(options['local_settings']) > 0 \
        and os.path.exists(options['local_settings']):
            dst = os.path.join(app_dir, 'settings.py')
            print_message(f'Appending {options["local_settings"]} to {dst}', self.verbosity)
            with open(dst, 'a') as settings_file:
                with open(options['local_settings'], 'r') as local_settings:
                    settings_file.write('\n')
                    settings_file.write(local_settings.read())
            print_message('Done.', self.verbosity)

    def deploy_askbot(self, options):
        """function that creates django project files,
        all the neccessary directories for askbot,
        and the log file
        """

        create_new_project = True
        if os.path.exists(options['dir_name']) and \
           path_utils.has_existing_django_project(options['dir_name']) and \
           options.force is False:
             create_new_project = False

        options['staticfiles_app'] = "'django.contrib.staticfiles',"
        options['auth_context_processor'] = 'django.contrib.auth.context_processors.auth'

        if create_new_project is True:
            self._create_new_django_project(options['dir_name'], options)

        self._create_new_django_app('askbot_app', options)

        help_file = path_utils.get_path_to_help_file()

        if create_new_project:
            print_message(
                messages.HOW_TO_DEPLOY_NEW % {'help_file': help_file},
                self.verbosity
            )
        else:
            print_message(
                messages.HOW_TO_ADD_ASKBOT_TO_DJANGO % {'help_file': help_file},
                self.verbosity
            )

# set to askbot_setup_orig to return to original installer
askbot_setup = AskbotSetup(interactive=True, verbosity=1)

def askbot_setup_orig():
    """basic deployment procedure
    asks user several questions, then either creates
    new deployment (in the case of new installation)
    or gives hints on how to add askbot to an existing
    Django project
    """
    parser = OptionParser(usage = "%prog [options]")

    parser.add_option(
                "-v", "--verbose",
                dest = "verbosity",
                type = "int",
                default = 1,
                help = "verbosity level available values 0, 1, 2."
            )

    parser.add_option(
                "-n", "--dir-name",
                dest = "dir_name",
                default = None,
                help = "Directory where you want to install."
            )

    parser.add_option(
                '-e', '--db-engine',
                dest='database_engine',
                action='store',
                type='choice',
                choices=DATABASE_ENGINE_CHOICES,
                default=None,
                help='Database engine, type 1 for postgresql, 2 for sqlite, 3 for mysql'
            )

    parser.add_option(
                "-d", "--db-name",
                dest = "database_name",
                default = None,
                help = "The database name"
            )

    parser.add_option(
                "-u", "--db-user",
                dest = "database_user",
                default = None,
                help = "The database user"
            )

    parser.add_option(
                "-p", "--db-password",
                dest = "database_password",
                default = None,
                help = "the database password"
            )

    parser.add_option(
                "--db-host",
                dest = "database_host",
                default = None,
                help = "the database host"
            )

    parser.add_option(
                "--db-port",
                dest = "database_port",
                default = None,
                help = "the database host"
            )

    parser.add_option(
                "--logfile-name",
                dest="logfile_name",
                default='askbot.log',
                help="name of the askbot logfile."
            )

    parser.add_option(
                "--append-settings",
                dest = "local_settings",
                default = '',
                help = "Extra settings file to append custom settings"
            )

    parser.add_option(
                "--force",
                dest="force",
                action='store_true',
                default=False,
                help = "Force overwrite settings.py file"
            )
    parser.add_option(
                "--no-secret-key",
                dest="no_secret_key",
                action='store_true',
                default=False,
                help="Don't generate a secret key. (not recommended)"
            )

    try:
        options = parser.parse_args()[0]

        #ask users to give missing parameters
        #todo: make this more explicit here
        if options.verbosity >= 1:
            print(messages.DEPLOY_PREAMBLE)

        directory = path_utils.clean_directory(options.dir_name)
        while directory is None:
            directory = path_utils.get_install_directory(force=options.force)
        options.dir_name = directory

        if options.database_engine not in DATABASE_ENGINE_CHOICES:
            options.database_engine = console.choice_dialog(
                'Please select database engine:\n1 - for postgresql, '
                '2 - for sqlite, 3 - for mysql, 4 - oracle',
                choices=DATABASE_ENGINE_CHOICES
            )

        options_dict = vars(options)
        if options.force is False:
            options_dict = collect_missing_options(options_dict)

        database_engine_codes = {
            '1': 'postgresql_psycopg2',
            '2': 'sqlite3',
            '3': 'mysql',
            '4': 'oracle'
        }
        database_engine = database_engine_codes[options.database_engine]
        options_dict['database_engine'] = database_engine

        deploy_askbot(options_dict)

        if database_engine == 'postgresql_psycopg2':
            try:
                import psycopg2
            except ImportError:
                print('\nNEXT STEPS: install python binding for postgresql')
                print('pip install psycopg2\n')
        elif database_engine == 'mysql':
            try:
                import _mysql
            except ImportError:
                print('\nNEXT STEP: install python binding for mysql')
                print('pip install mysql-python\n')

    except KeyboardInterrupt:
        print("\n\nAborted.")
        sys.exit(1)


#separated all the directory creation process to make it more useful
def deploy_askbot(options):
    """function that creates django project files,
    all the neccessary directories for askbot,
    and the log file
    """
    create_new_project = True
    if os.path.exists(options['dir_name']):
        if path_utils.has_existing_django_project(options['dir_name']):
            create_new_project = bool(options['force'])

    path_utils.create_path(options['dir_name'])

    options['staticfiles_app'] = "'django.contrib.staticfiles',"

    options['auth_context_processor'] = 'django.contrib.auth.context_processors.auth'

    verbosity = options['verbosity']

    path_utils.deploy_into(
        options['dir_name'],
        new_project=create_new_project,
        verbosity=verbosity,
        context=options
    )

    help_file = path_utils.get_path_to_help_file()

    if create_new_project:
        print_message(
            messages.HOW_TO_DEPLOY_NEW % {'help_file': help_file},
            verbosity
        )
    else:
        print_message(
            messages.HOW_TO_ADD_ASKBOT_TO_DJANGO % {'help_file': help_file},
            verbosity
        )

def collect_missing_options(options_dict):
    options_dict['secret_key'] = '' if options_dict['no_secret_key'] else generate_random_key()
    if options_dict['database_engine'] == '2':#sqlite
        if options_dict['database_name']:
            return options_dict
        while True:
            value = console.simple_dialog(
                            'Please enter database file name'
                        )
            database_file_name = None
            if os.path.isfile(value):
                message = 'file %s exists, use it anyway?' % value
                if console.get_yes_or_no(message) == 'yes':
                    database_file_name = value
            elif os.path.isdir(value):
                print('%s is a directory, choose another name' % value)
            elif value in path_utils.FILES_TO_CREATE:
                print('name %s cannot be used for the database name' % value)
            elif value == path_utils.LOG_DIR_NAME:
                print('name %s cannot be used for the database name' % value)
            else:
                database_file_name = value

            if database_file_name:
                options_dict['database_name'] = database_file_name
                return options_dict

    else:#others
        db_keys = OrderedDict([
            ('database_name', True),
            ('database_user', True),
            ('database_password', True),
            ('database_host', False),
            ('database_port', False)
        ])
        for key, required in list(db_keys.items()):
            if options_dict[key] is None:
                key_name = key.replace('_', ' ')
                fmt_string = '\nPlease enter %s'
                if not required:
                    fmt_string += ' (press "Enter" to use the default value)'

                value = console.simple_dialog(
                    fmt_string % key_name,
                    required=db_keys[key]
                )

                options_dict[key] = value
        return options_dict
