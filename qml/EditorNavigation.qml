import QtQuick 2.15

QtObject {
    id: root
    property var theme
    property var controller
    property var field
    property var keypad
    enum Focus { Keys, FieldWithKeys, FieldWithActions, RevealWithKeys, RevealWithActions, Actions }
    property int focusState: EditorNavigation.Keys
    readonly property bool keyboardVisible: focusState === EditorNavigation.Keys
        || focusState === EditorNavigation.FieldWithKeys || focusState === EditorNavigation.RevealWithKeys
    readonly property string focusZone: focusState === EditorNavigation.Keys ? "keys"
        : focusState === EditorNavigation.Actions ? "actions"
        : focusState === EditorNavigation.FieldWithKeys || focusState === EditorNavigation.FieldWithActions
          ? "field" : "reveal"
    property int actionIndex: 1
    signal submitRequested()
    signal cancelRequested()

    function reset(numeric) {
        focusState = EditorNavigation.Keys
        actionIndex = 1
        keypad.reset(numeric)
        keypad.selectionActive = theme.navigationFocus
    }

    function focusKeys() {
        focusState = EditorNavigation.Keys
        keypad.selectionActive = theme.navigationFocus
    }

    function focusActions() {
        focusState = EditorNavigation.Actions
        keypad.selectionActive = false
    }

    function toggleKeyboard() {
        if (keyboardVisible) focusActions()
        else focusKeys()
    }

    function touchField() {
        focusState = EditorNavigation.Keys
        keypad.selectionActive = false
    }

    function handleAction(action) {
        if (action !== "left" && action !== "right" && action !== "up"
                && action !== "down" && action !== "select") return false
        theme.inputMode = Theme.Navigation

        if (focusZone === "keys") {
            if (!keypad.selectionActive) {
                keypad.selectionActive = true
            } else if (action === "up" && keypad.currentRow === 0) {
                focusState = keyboardVisible ? EditorNavigation.FieldWithKeys : EditorNavigation.FieldWithActions
                keypad.selectionActive = false
            } else if (action === "down" && keypad.currentRow === keypad.rowCount - 1) {
                focusActions()
            } else {
                keypad.handleAction(action)
            }
        } else if (focusZone === "field") {
            if (action === "left" || action === "right") {
                if (action === "right" && field.secret
                        && field.editor.cursorPosition === field.text.length) {
                    focusState = keyboardVisible ? EditorNavigation.RevealWithKeys : EditorNavigation.RevealWithActions
                } else {
                    field.editor.deselect()
                    field.editor.cursorPosition = controller.textCursorPosition(
                        field.text, field.editor.cursorPosition, action === "left" ? -1 : 1)
                }
            } else if (action === "up") {
                focusActions()
            } else {
                focusKeys()
            }
        } else if (focusZone === "reveal") {
            if (action === "select") field.toggleReveal()
            else if (action === "left") focusState = keyboardVisible ? EditorNavigation.FieldWithKeys : EditorNavigation.FieldWithActions
            else if (action === "down") focusKeys()
            else focusActions()
        } else {
            if (action === "left" || action === "right") actionIndex = 1 - actionIndex
            else if (action === "up") focusState = keyboardVisible ? EditorNavigation.FieldWithKeys : EditorNavigation.FieldWithActions
            else if (action === "down") focusKeys()
            else if (actionIndex === 0) cancelRequested()
            else submitRequested()
        }
        return true
    }
}
