import sublime
import sublime_plugin
import os
import sys
import codecs
import urllib
import re
import threading
import subprocess
from html.parser import HTMLParser

VERSION = "0.2b"

# English Dictionary: Naver
WEB_ENGLISH_DIC_URL = "http://endic.naver.com/search.nhn?%s"
WEB_ENGLISH_DIC_OPTIONS = "query={query}&searchOption=thesaurus"

# Korean Dictionary: Naver
WEB_KOREAN_DIC_URL = "http://krdic.naver.com/search.nhn?kind=all&%s"
WEB_KOREAN_DIC_OPTIONS = "query={query}"

# Japanese Dictionary: Naver
WEB_JAPANESE_DIC_URL = "http://jpdic.naver.com/search.nhn?range=word&%s"
WEB_JAPANESE_DIC_OPTIONS = "q={query}"

TIMEOUT_SECONDS = 20

ENGLISH_TARGET_BLOCK_TAG = 'span'
ENGLISH_TARGET_SYNONYM_TAG = 'a'
ENGLISH_TARGET_SYNONYM_LABEL = '[유의어]'


MAX_QUERY_DEPTH = 20
KOREAN_TARGET_SYNONYM_TAG = 'a'
KOREAN_TARGET_SYNONYM_CLASS_ID = 'syno'
KOREAN_TARGET_BLOCK_TAG = 'span'
KOREAN_TARGET_BLOCK_CLASS_ID = 'head_word'
KOREAN_TARGET_BLOCK_END_TAG = 'div'
KOREAN_TARGET_BLOCK_END_CLASS_ID = 'btn_showmore'
KOREAN_TARGET_KEYWORD_TAG = 'strong'
JAPANESE_TARGET_BLOCK_TAG = 'span'
JAPANESE_TARGET_KEYWORD = '[유의어]'
JAPANESE_TARGET_SYNONYM_TAG = 'a'

MIN_WORD_LEN = 2
MAX_WORD_LEN = 100
CUSTOM_DICTIONARY_COMMENT_CHAR = '#'

MAX_AUTOCOMPLETE_SUGGETIONS = 100

DEFAULT_WEB_DIC_DISPLAY_METHOD = 'quick_panel'


class cwkBase:
    def __init__(self):
        self.plugin_settings = sublime.load_settings("cwkWritingToolKit.sublime-settings")
        self.debug = self.plugin_settings.get("debug", False)
        self.read_aloud = self.plugin_settings.get("read_aloud_current_word", False)
        self.english_voice = self.plugin_settings.get("english_voice", False)
        self.korean_voice = self.plugin_settings.get("korean_voice", False)
        self.japanese_voice = self.plugin_settings.get("japanese_voice", False)
        self.corpus_extensions = self.plugin_settings.get("corpus_extensions", [])
        self.custom_dictionary_extensions = self.plugin_settings.get("custom_dictionary_extensions", ['.cwkcsv',])
        self.force_rebuild_corpus_on_every_save = self.plugin_settings.get("force_rebuild_corpus_on_every_save", True)
        self.max_autocomplete_suggestions = self.plugin_settings.get("max_autocomplete_suggestions", MAX_AUTOCOMPLETE_SUGGETIONS)
        self.web_dic_display_method = self.plugin_settings.get("web_dic_display_method", DEFAULT_WEB_DIC_DISPLAY_METHOD)

        self._words = []

    def isKorean(self, word):
        if re.match(r'(^[가-힣]+)', word):
            return True
        else:
            return False

    def isEnglish(self, word):
        if re.match(r'(^[a-zA-Z]+)', word):
            return True
        else:
            return False

    def isJapanese(self, word):
        if re.match(r'[一-龠あ-んア-ン]+', word):
            return True
        else:
            return False

    def isCorpusFile(self, filename):
        """check if the given file should be parsed
        """
        try:
            fname, fextension = os.path.splitext(filename)
            return fextension in self.corpus_extensions
        except (AttributeError, TypeError) as e:
            self.log("Error reading {filename}: {error}".format(filename=filename, error=e))
            return False

    def isDictionaryFile(self, filename):
        """check if the given file is a dictionary
        """
        try:
            fname, fextension = os.path.splitext(filename)
            return fextension in self.custom_dictionary_extensions
        except (AttributeError, TypeError) as e:
            self.log("Error reading {filename}: {error}".format(filename=filename, error=e))
            return False

    def removeTags(self, line):
        """clean up HTML tags
        """
        pattern = re.compile(r'<[^>]+>')
        return pattern.sub('', line)

    def readAloud(self, message):
        """Mac OSX only: read alound the given message using system voices
        """

        if sys.platform != 'darwin':
            return

        if message:
            voice = ""
            if self.isEnglish(message):
                voice = self.english_voice
            elif self.isKorean(message):
                voice = self.korean_voice
            elif self.isJapanese(message):
                voice = self.japanese_voice

            shell_command = ["/usr/bin/say", "-v", voice, message]
            subprocess.call(shell_command)

    def log(self, message):
        """utility method to print out debug messages
        """

        if(self.debug):
            print ("[cwk log] ==  {msg}".format(msg=message))

class cwkWord:
    _name = ""
    _filename = ""

    def __init__(self, name, filename):
        self._name = name
        self._filename = filename

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = value

    @property
    def filename(self):
        return self._filename

    @filename.setter
    def filename(self, value):
        self._filename = value


class cwkCorpus(cwkBase):
    def __init__(self):
        self._words = []
        cwkBase.__init__(self)

    def clearCorpus(self):
        self._words = []

    def numWords(self):
        return len(self._words)

    def addWord(self, name, filename):
        self._words.append(cwkWord(name, filename))

    def get_autocomplete_list(self, word):
        autocomplete_list = []
        seen = []
        word_count = 0
        for auto_word in self._words:
            if word_count > self.max_autocomplete_suggestions:
                break
            if word in auto_word.name:
                if self.isCorpusFile(auto_word.filename) and auto_word.name in seen:
                    continue
                seen.append(auto_word.name)
                if self.isCorpusFile(auto_word.filename):
                    label = auto_word.name + '\t' + auto_word.filename
                    str_to_insert = auto_word.name
                else:
                    label = auto_word.name + '\t' + auto_word.filename
                    str_to_insert = auto_word.filename
                autocomplete_list.append((label, str_to_insert))
                word_count += 1
        return autocomplete_list


class cwkWordsCollectorThread(cwkBase, threading.Thread):
    def __init__(self, collector, open_folders):
        self.collector = collector
        self.time_out_seconds = TIMEOUT_SECONDS
        self.open_folders = open_folders
        threading.Thread.__init__(self)
        cwkBase.__init__(self)

    def run(self):
        files = []
        for folder in self.open_folders:
            # skip archives
            if "/_" in folder:
                self.log("Skipping the archived folder: {name}".format(name=folder))
                continue
            files = self.getWordFiles(folder)
            num_files = len(files)
            for filename in files:
                if "/_" in filename:
                    self.log("Skipping the archived file or folder: {name}".format(name=filename))
                    num_files = num_files - 1
                    continue
                self.collectWords(filename)
        if files:
            self.log("{num_words} word(s) found in {num_files} corpus file(s)".format(num_words=self.collector.numWords(), num_files=num_files))
        else:
            self.log("No corpus file found.")

    def stop(self):
        if self.isAlive():
            try:
                self._Thread__stop()
            except AttributeError as e:
                self.log("Thread error: {error}".format(error=e))

    def getWordFiles(self, folder, *args):
        """resursive method parsing every corpus and dictionary file in the given folder and its subfolders
        """

        autocomplete_word_files = []
        for file in os.listdir(folder):
            if file.startswith('.'):
                continue
            fullpath = os.path.join(folder, file)

            if os.path.isfile(fullpath) and (self.isCorpusFile(fullpath) or self.isDictionaryFile(fullpath)):
                autocomplete_word_files.append(fullpath)
            elif os.path.isdir(fullpath):
                autocomplete_word_files += self.getWordFiles(fullpath, *args)
        return autocomplete_word_files

    def collectWords(self, filename):
        file_lines = codecs.open(filename, "r", "utf-8")
        if self.isCorpusFile(filename):
            # english, korean, japanese regex patterns
            pattern = re.compile(r'([\w가-힣一-龠あ-んア-ン]+)')
            for line in file_lines:
                for m in re.findall(pattern, line):
                    if len(m) > MIN_WORD_LEN and len(m) < MAX_WORD_LEN:
                        self.collector.addWord(m, os.path.basename(filename))

        elif self.isDictionaryFile(filename):
            for line in file_lines:
                line = line.strip()
                if line.startswith(CUSTOM_DICTIONARY_COMMENT_CHAR): 
                    continue
                words = [w.strip() for w in line.split(',') if w != '']
                if words:
                    keyword = words[0]
                    words = words[1:]
                    for w in words:
                        self.collector.addWord(keyword, w)


class cwkWebDicParser(HTMLParser, cwkBase):
    def __init__(self, view):
        HTMLParser.__init__(self)
        cwkBase.__init__(self)
        self.view = view

    def getWordsFromWebDictionary(self):
        return self._words


class cwkEnglishWebDicParser(cwkWebDicParser):
    def __init__(self, view):
        cwkWebDicParser.__init__(self, view)
        self._is_in_block = False
        self._ENGLISH_TARGET_BLOCK_TAG_found = False
        self._ENGLISH_TARGET_SYNONYM_TAG_found = False
        self._target_defs_tag_found = False
        self._is_final_tag = False
        self.synonym = ''

    def handle_starttag(self, tag, attrs):
        if tag == ENGLISH_TARGET_BLOCK_TAG:
            # target tag found

            if self._is_in_block and self._is_final_tag:
                self.reset_tags()
                self._target_defs_tag_found = True
            else:
                self._ENGLISH_TARGET_BLOCK_TAG_found = True

        elif tag == ENGLISH_TARGET_SYNONYM_TAG and self._is_in_block:
            # synonym tag found

            self._ENGLISH_TARGET_SYNONYM_TAG_found = True
        else:
            # false alarm

            self.reset_tags()

    def handle_endtag(self, tag):
        pass

    def handle_data(self, data):
        if not self._is_in_block and self._ENGLISH_TARGET_BLOCK_TAG_found and data.strip() == ENGLISH_TARGET_SYNONYM_LABEL:
            #keyword found: block starts.
            self._is_in_block = True
        elif self._is_in_block and self._ENGLISH_TARGET_SYNONYM_TAG_found:
            #synonym tag found: gather synonym

            self.synonym = data
            self._ENGLISH_TARGET_SYNONYM_TAG_found = False
            self._is_final_tag = True
        elif self._target_defs_tag_found:
            # synonym definitions found: gather defs

            defs = data.split(",")
            self._words.append(self.synonym)
            self.log("appending synonym: " + self.synonym)
            self.view.set_status('cwkWritingToolKit', 'Add synonym: '+self.synonym)
            for d in defs:
                self._words.append("\t {0}".format(d))
                self.log("appending def: "+d)
                self.view.set_status('cwkWritingToolKit', 'Adding definition: '+d)
            self.synonym = ''
            self.reset_tags()
        else:
            # reset and get ready to go again

            self.reset_tags()

    def reset_tags(self):
        self._is_in_block = False
        self._ENGLISH_TARGET_BLOCK_TAG_found = False
        self._ENGLISH_TARGET_SYNONYM_TAG_found = False
        self._target_defs_tag_found = False
        self._is_final_tag = False


class cwkKoreanWebDicParser(cwkWebDicParser):
    def __init__(self, view):
        cwkWebDicParser.__init__(self, view)
        self._target_synonym_found = False
        self._target_keyword_tag_found = False
        self._is_in_block = False

    def handle_starttag(self, tag, attrs):
        if tag == KOREAN_TARGET_BLOCK_TAG:
            for name, value in attrs:
                if name == 'class' and value == KOREAN_TARGET_BLOCK_CLASS_ID:
                    self._is_in_block = True
        if tag == KOREAN_TARGET_BLOCK_END_TAG:
            for name, value in attrs:
                if name == 'class' and value == KOREAN_TARGET_BLOCK_END_CLASS_ID:
                    self._is_in_block = False
                    self.reset_tags()

        if self._is_in_block:
            if tag == KOREAN_TARGET_SYNONYM_TAG:
                for name, value in attrs:
                    if name == 'class' and value == KOREAN_TARGET_SYNONYM_CLASS_ID:
                        self._target_synonym_found = True
            elif tag == KOREAN_TARGET_KEYWORD_TAG:
                self._target_keyword_tag_found = True
            else:
                # false alarm
                self.reset_tags()

    def handle_endtag(self, tag):
        pass

    def handle_data(self, data):
        data = self.removeTags(data)
        if self._target_synonym_found:
            if self.isKorean(data):
                self._words.append("\t" + data)
                self.log("appending synonym: " + data)
                self.view.set_status('cwkWritingToolKit', 'Adding synonym: '+data)

        if self._target_keyword_tag_found:
            self._words.append(data)
            self.log("appending keyword: " + data)
            self.view.set_status('cwkWritingToolKit', 'Adding keyword: '+data)
            self._target_keyword_tag_found = False

    def reset_tags(self):
        self._target_synonym_found = False
        self._target_keyword_tag_found = False


class CwkWebDicFetcherThread(cwkBase, threading.Thread):

    def __init__(self, search_keyword, window, view, force_mode):
        cwkBase.__init__(self)
        self.search_keyword = search_keyword
        self.window = window
        self.view = view
        self.timeout_seconds = TIMEOUT_SECONDS
        self._query_depth = 0
        self._words = []
        self.force_mode = force_mode
        threading.Thread.__init__(self)

    def run(self):
        if self.search_keyword:
            self.view.set_status('cwkWritingToolKit', 'Starting web dic thread')
            if self.force_mode == 'Korean':
                self._words = []
                self.fetchKoreanSynonyms(self.search_keyword)
            elif self.force_mode == 'English':
                encoded_query = urllib.parse.quote(self.search_keyword)
                options = WEB_ENGLISH_DIC_OPTIONS.format(query=encoded_query)
                request = urllib.request.Request(WEB_ENGLISH_DIC_URL % options)
                response = urllib.request.urlopen(request)
                webpage = response.read().decode('utf-8')

                parser = cwkEnglishWebDicParser(self.view)

                parser.feed(webpage)
                self._words = parser.getWordsFromWebDictionary()
            elif self.force_mode == 'Japanese':
                self.log("Feature not implemented yet.")
            else:
                if self.isEnglish(self.search_keyword):
                    encoded_query = urllib.parse.quote(self.search_keyword)
                    options = WEB_ENGLISH_DIC_OPTIONS.format(query=encoded_query)
                    request = urllib.request.Request(WEB_ENGLISH_DIC_URL % options)
                    response = urllib.request.urlopen(request)
                    webpage = response.read().decode('utf-8')

                    parser = cwkEnglishWebDicParser(self.view)

                    parser.feed(webpage)
                    self._words = parser.getWordsFromWebDictionary()

                elif self.isKorean(self.search_keyword):
                    self._words = []
                    self.fetchKoreanSynonyms(self.search_keyword)
                elif self.isJapanese(self.search_keyword):
                    self.log("Feature not implemented yet.")
            log_message = "{num} synonym(s) found for '{word}'".format(num=len(self._words), word=self.search_keyword)
            self.log(log_message)
            self.view.set_status('cwkWritingToolKit', log_message)
            if self._words:
                self.showWebDic()

    def showWebDic(self):

        if self.web_dic_display_method == 'popup':
            self.view.show_popup_menu(self._words, self.replaceSelectedWord)
        elif self.web_dic_display_method == 'quick_panel':
            self.window.show_quick_panel(self._words, self.replaceSelectedWord)
        else:
            self.log("Unknown web dic display method: {}".format(self.web_dic_display_method))

    def fetchKoreanSynonyms(self, word):
        """resursively fetches synonyms until _query_depth > MAX_QUERY_DEPTH
        """

        self._query_depth += 1

        if self._query_depth > MAX_QUERY_DEPTH: 
            return

        encoded_query = urllib.parse.quote(word)
        options = WEB_KOREAN_DIC_OPTIONS.format(query=encoded_query)
        request = urllib.request.Request(WEB_KOREAN_DIC_URL % options)

        response = urllib.request.urlopen(request)
        webpage = response.read().decode('utf-8')

        parser = cwkKoreanWebDicParser(self.view)

        parser.feed(webpage)
        for s in parser.getWordsFromWebDictionary():
            if s not in self._words:
                self._words.append(s)

        for s in parser.getWordsFromWebDictionary():
            if s.startswith("\t"):
                self.fetchKoreanSynonyms(s)

    def stop(self):
        if self.isAlive():
            self._Thread__stop()

    def replaceSelectedWord(self, index):
        """showWebDic callback method
        """
        # if the use canceled out of the selection menu, -1 is returned. Otherwise the index is returned.

        if index == -1: 
            return

        selected_string = self._words[index]

        # run Text Command cwk_insert_selected_text to replace the current word with the user's choice

        self.view.run_command("cwk_insert_selected_text", {"args": {'text': selected_string.strip()} })

# cwk_fetch_WEB_ENGLISH_DIC text command inserts one of the synonym definitions fetched from the given web dictionary.
# camel casing: CwkFetchWebDic
# snake casing: cwk_fetch_web_dic
# Sublime Text translates camel cased commands into snake cased ones.
# You can run snake cased command by calling the view's run_command() method as the following:
#     view.run_command("cwk_fetch_web_dic", text_to_insert)


class CwkFetchWebDic(sublime_plugin.TextCommand, cwkBase):

    def __init__(self, *args, **kwargs):
        sublime_plugin.TextCommand.__init__(self, *args, **kwargs)
        cwkBase.__init__(self)
        self._fetcher_thread = None
        self.force_mode = False

    def run(self, edit, force_mode=False):

        self.force_mode = force_mode

        # get active window and view
        window = sublime.active_window()
        view = window.active_view()

        # save the word at the cursor position

        self.currentWord = view.substr(view.word(view.sel()[0].begin()))
        self.readAloud(self.currentWord)

        self._words = []
        if self._fetcher_thread is not None:
            self._fetcher_thread.stop()
        self._fetcher_thread = CwkWebDicFetcherThread(self.currentWord, window, view, force_mode)
        self._fetcher_thread.start()
        self.log("web dic thread started")

# cwk_insert_selected_text command inserts text at cursor position
# camel casing: CwkInsertSelectedText
# snake casing: cwk_insert_selected_text
# Sublime Text translates camel cased commands into snake cased ones.
# You can run snake cased command by calling the view's run_command() method as the following:
#     view.run_command("cwk_insert_selected_text", text_to_insert)


class CwkInsertSelectedText(sublime_plugin.TextCommand, cwkBase):
    def __init__(self, *args, **kwargs):
        sublime_plugin.TextCommand.__init__(self, *args, **kwargs)
        cwkBase.__init__(self)

    def run(self, edit, args):

        # get current cursor position
        # Sublime Text supports multiple cursors: view.sel() returns the list of those cursors. The first element of the list refers to the current cursor position.
        # view.word() returns the region of the current word.

        cursor = self.view.sel()[0]
        word_region = self.view.word(cursor)
        word = self.view.substr(word_region)

        # view.replace() replaces the selected word with the given text. edit is the buffer currently in use.

        self.view.replace(edit, word_region, args['text'])

        self.readAloud(args['text'])


class CwkWebDic(sublime_plugin.WindowCommand, cwkBase):
    def __init__(self, window):

        # super() refers to the immediate ancestor: sublime_plugin.WindowCommand in this case.

        super().__init__(window)
        cwkBase.__init__(self)

        # get active window and view

        window = sublime.active_window()
        view = window.active_view()

        # save the word at the cursor position

        self.currentWord = view.substr(view.word(view.sel()[0].begin()))

        # self._words stores all found words whereas self._normalizedWords stores unique values.
        self._normalizedWords = []

    def run(self):
        """run method is triggered when this cwk_auto_comoplete command is called
        """

        window = sublime.active_window()
        view = window.active_view()

        # self.log() spits out messages only when debug mode is on, that is, set to true.
        self.currentWord = view.substr(view.word(view.sel()[0].begin()))

        self.readAloud(self.currentWord)

        self.normalizeWords()

        # view.shop_popup_menu() displays a popout menu presenting the words that contain the self.currentWord.
        # self.on_done is a callback method to be called when a selection is made.

        view.show_popup_menu(self._normalizedWords, self.on_done)

    def on_done(self, index):
        """show_popup_menu callback method
        """
        # if the use canceled out of the popout menu, -1 is returned. Otherwise the index is returned.

        if index == -1:
            return

        selected_string = self._normalizedWords[index]
        window = sublime.active_window()
        view = window.active_view()

        # run Text Command cwk_insert_selected_text to replace the current word with the user's choices

        view.run_command("cwk_insert_selected_text", {"args": {'text': selected_string.strip()} })

    def normalizeWords(self):
        """selects only those words that match the current word
        """

        # Python idiom: list comprehension
        # discards the words not matching the current word and strip whitespaces at both ends
        if self._words:
            self._normalizedWords = [w.strip() for w in self._words if self.currentWord in w]


class CwkAutoComplete(cwkCorpus, cwkBase, sublime_plugin.EventListener):

    _collector_thread = None
    _window_id = None
    _corpus_built = False

    def buildCorpus(self):

        window = sublime.active_window()

        # corpus already built for this project
        settings = cwkBase()
        if self._corpus_built and window.id() == self._window_id and not settings.force_rebuild_corpus_on_every_save: return

        self._window_id = window.id()
        view = window.active_view()

        self.clearCorpus()
        self._corpus_built = True

        open_folders = view.window().folders()
        cwkBase.log(self, "building corpus for window id {id}".format(id=self._window_id))
        if self._collector_thread is not None:
            self._collector_thread.stop()
        self._collector_thread = cwkWordsCollectorThread(self, open_folders)
        self._collector_thread.start()

    def on_post_save(self, view):
        self.buildCorpus()

    def on_query_completions(self, view, prefix, locations):
        current_file = view.file_name()
        completion_flags = (
            sublime.INHIBIT_WORD_COMPLETIONS |
            sublime.INHIBIT_EXPLICIT_COMPLETIONS
        )
        completions = []
        if self.isCorpusFile(current_file):
            return self.get_autocomplete_list(prefix)
            completions.sort()
        return (completions, completion_flags)
