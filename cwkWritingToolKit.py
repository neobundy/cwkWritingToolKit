import sublime, sublime_plugin

VERSION = "0.01"

class CwkInsertSelectedText(sublime_plugin.TextCommand):

	def run(self, edit, args):
		self.view.insert(edit, self.view.sel()[0].begin(), args['text'])

class CwkAutoComplete(sublime_plugin.WindowCommand):

	def __init__(self, window):

		self.plugin_settings = sublime.load_settings("cwkWritingToolKit.sublime-settings")
		super().__init__(window)
		self._words = ["foo", "bar"]
		self.window = sublime.active_window()
		self.view = window.active_view()

	def run(self):
		self.debug = self.plugin_settings.get("debug", False)
		self.view.show_popup_menu(self._words, self.on_done)

	def on_done(self, index):
		if index == -1: return
		selected_string = self._words[index]
		self.log("Word selected: " , selected_string)
		self.view.run_command("cwk_insert_selected_text", {"args": {'text': selected_string} })

	def log(self, *message):
		if(self.debug):
			print (*message)


			