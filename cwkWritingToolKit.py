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

	def run(self):
		self.debug = self.plugin_settings.get("debug", False)
		window = sublime.active_window()
		view = window.active_view()
		self.log("view id: ", view.view_id)

		view.show_popup_menu(self._words, self.on_done)

	def on_done(self, index):
		if index == -1: return
		selected_string = self._words[index]
		self.log("Word selected: " , selected_string)
		window = sublime.active_window()
		view = window.active_view()
		view.run_command("cwk_insert_selected_text", {"args": {'text': selected_string} })

	def log(self, *message):
		if(self.debug):
			print (*message)


