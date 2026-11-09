import QtQuick 2.15

Item {
    id: root
    objectName: "settingsKeyboardLayer"
    property var theme
    property var translator
    property var controller
    property var definition: ({})
    property alias valueText: editorField.text
    property alias secretRevealed: editorField.revealed
    property string errorText: ""
    readonly property bool keyboardVisible: navigation.keyboardVisible
    readonly property bool secret: Boolean(definition.secret)
    readonly property bool numberInput: String(definition.kind || "") === "number"
    readonly property string activeLanguage: translator
        ? String(translator.language) : "en"
    signal saveRequested(string value)
    signal cancelRequested()

    function translatedText(key) {
        var language = activeLanguage
        return translator.text(String(key))
    }

    function begin(valueDefinition) {
        definition = valueDefinition || ({})
        valueText = String(definition.value === undefined ? "" : definition.value)
        editorField.conceal()
        navigation.reset(numberInput)
        Qt.callLater(function() {
            if (!root.visible) return
            editorField.editor.cursorPosition = editorField.text.length
            editorField.editor.forceActiveFocus()
        })
    }

    function insertText(text) { keyboard.insert(String(text)) }
    function deletePreviousCharacter() { keyboard.erase() }
    function toggleKeyboard() {
        navigation.toggleKeyboard()
    }
    function handleKeyboardAction(action) {
        return navigation.handleAction(action)
    }
    function saveValue() { root.saveRequested(editorField.text) }

    onVisibleChanged: if (!visible) editorField.editor.focus = false

    EditorNavigation {
        id: navigation
        theme: root.theme
        controller: root.controller
        field: editorField
        keypad: keyboard
        onSubmitRequested: root.saveValue()
        onCancelRequested: root.cancelRequested()
    }

    Rectangle { anchors.fill: parent; color: root.theme.paper }
    MouseArea { anchors.fill: parent }

    PageHeader {
        id: editorHeader
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.leftMargin: root.theme.outerMargin
        anchors.rightMargin: root.theme.outerMargin
        theme: root.theme
        backVisible: true
        onBackRequested: root.cancelRequested()
        title: String(root.definition.editorTitle || "")
    }

    TextEntry {
        id: editorField
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: editorHeader.bottom
        anchors.leftMargin: root.theme.outerMargin
        anchors.rightMargin: root.theme.outerMargin
        anchors.topMargin: root.theme.compactMargin
        height: Math.max(Math.round(64 * root.theme.scale), implicitHeight)
        theme: root.theme
        translator: root.translator
        secret: root.secret
        numeric: root.numberInput
        unitText: root.numberInput ? String(root.definition.unitText) : ""
        invalid: root.errorText.length > 0
        navigationSelected: navigation.focusZone === "field"
        revealSelected: navigation.focusZone === "reveal"
        placeholder: root.translatedText(root.secret
            ? "keyboard.enter_api_token" : "keyboard.enter_value")
        onActivated: navigation.focusKeys()
        onTouched: navigation.touchField()
        onNavigationRequested: function(action) { navigation.handleAction(action) }
        onAccepted: root.saveValue()
    }

    Flickable {
        id: editorMessages
        anchors.left: editorField.left
        anchors.right: editorField.right
        anchors.top: editorField.bottom
        anchors.bottom: keyboard.visible ? keyboard.top : actions.top
        anchors.topMargin: root.theme.compactMargin
        anchors.bottomMargin: root.theme.compactMargin
        contentWidth: width
        contentHeight: editorMessage.implicitHeight
        interactive: contentHeight > height
        clip: true
        boundsBehavior: Flickable.StopAtBounds

        Text {
            id: editorMessage
            width: editorMessages.width
            text: root.errorText.length > 0 ? root.errorText
                  : root.numberInput ? String(root.definition.rangeHint)
                  : root.theme.navigationFocus && navigation.focusZone !== "actions" ? root.translatedText(
                        root.keyboardVisible && navigation.focusZone === "keys"
                            ? "keyboard.navigation_hint" : "keyboard.cursor_hint") : ""
            textFormat: Text.PlainText
            color: root.theme.ink
            font.family: root.theme.bodyFont
            font.pixelSize: root.theme.detailSize
            wrapMode: Text.Wrap
        }
    }

    ActionButtonRow {
        id: actions
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: root.theme.outerMargin
        visible: !root.keyboardVisible
        theme: root.theme
        leftText: root.translatedText("action.cancel")
        rightText: root.translatedText("action.save")
        leftSelected: navigation.focusZone === "actions" && navigation.actionIndex === 0
        rightSelected: navigation.focusZone === "actions" && navigation.actionIndex === 1
        onLeftRequested: root.cancelRequested()
        onRightRequested: root.saveValue()
    }

    Keyboard {
        id: keyboard
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: Math.round(root.height * root.theme.keyboardHeightRatio)
        visible: root.keyboardVisible
        theme: root.theme
        translator: root.translator
        target: editorField.editor
        submitLabel: root.translatedText("action.save")
        onSubmitRequested: root.saveValue()
    }
}
