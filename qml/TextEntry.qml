import QtQuick 2.15

Rectangle {
    id: root
    property var theme
    property var translator
    property alias editor: input
    property alias text: input.text
    property int maximumLength: 4096
    property string placeholder: ""
    property bool secret: false
    enum Privacy { Masked, Revealed }
    property int privacy: TextEntry.Masked
    readonly property bool revealed: privacy === TextEntry.Revealed
    function conceal() { privacy = TextEntry.Masked }
    function toggleReveal() { privacy = revealed ? TextEntry.Masked : TextEntry.Revealed }
    property bool numeric: false
    property string unitText: ""
    property bool invalid: false
    property bool navigationSelected: false
    property bool revealSelected: false
    signal activated()
    signal touched()
    signal navigationRequested(string action)
    signal accepted()

    implicitHeight: Math.max(theme.fieldSize, theme.controlSize) + theme.compactMargin * 2
    color: theme.paper
    border.color: theme.ink
    border.width: theme.controlBorderWidth
                  * (invalid || (theme.navigationFocus && navigationSelected) ? 2 : 1)

    TextInput {
        id: input
        objectName: "entryTextInput"
        anchors.left: parent.left
        anchors.right: unitLabel.visible ? unitLabel.left
                       : revealButton.visible ? revealButton.left : parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.margins: root.theme.compactMargin
        color: root.theme.ink
        selectionColor: root.theme.ink
        selectedTextColor: root.theme.paper
        font.family: root.theme.bodyFont
        font.pixelSize: root.theme.fieldSize
        verticalAlignment: TextInput.AlignVCenter
        selectByMouse: true
        clip: true
        maximumLength: root.maximumLength
        echoMode: root.secret && !root.revealed ? TextInput.Password : TextInput.Normal
        passwordMaskDelay: 0
        inputMethodHints: Qt.ImhNoPredictiveText | Qt.ImhNoAutoUppercase
            | (root.secret ? Qt.ImhSensitiveData | Qt.ImhHiddenText : 0)
            | (root.numeric ? Qt.ImhDigitsOnly : 0)
        onActiveFocusChanged: if (activeFocus) root.activated()
        onAccepted: root.accepted()
        Keys.priority: Keys.BeforeItem
        Keys.onPressed: function(event) {
            if (event.modifiers & (Qt.ControlModifier | Qt.MetaModifier
                                  | Qt.AltModifier | Qt.ShiftModifier)) return
            var action = ""
            if (event.key === Qt.Key_Left) action = "left"
            else if (event.key === Qt.Key_Right) action = "right"
            else if (event.key === Qt.Key_Up) action = "up"
            else if (event.key === Qt.Key_Down) action = "down"
            else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) action = "select"
            if (action.length === 0) return
            root.navigationRequested(action)
            event.accepted = true
        }
    }

    Text {
        anchors.fill: input
        visible: input.text.length === 0
        text: root.placeholder
        color: root.theme.ink
        font.family: root.theme.bodyFont
        font.pixelSize: root.theme.fieldSize
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    MouseArea {
        anchors.fill: input
        onPressed: {
            root.theme.inputMode = Theme.Touch
            root.touched()
            root.activated()
            mouse.accepted = false
        }
    }

    Text {
        id: unitLabel
        anchors.right: revealButton.visible ? revealButton.left : parent.right
        anchors.rightMargin: root.theme.compactMargin
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        visible: root.unitText.length > 0
        text: root.unitText
        textFormat: Text.PlainText
        color: root.theme.ink
        font.family: root.theme.bodyFont
        font.pixelSize: root.theme.controlSize
        verticalAlignment: Text.AlignVCenter
    }

    TextMetrics {
        id: revealMetrics
        text: revealButton.text
        font.family: root.theme.displayFont
        font.pixelSize: root.theme.controlSize
    }

    ActionButton {
        id: revealButton
        objectName: "entryRevealButton"
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.margins: root.theme.controlBorderWidth
        width: Math.max(Math.round(100 * root.theme.scale),
                        Math.ceil(revealMetrics.advanceWidth) + root.theme.compactMargin * 2)
        visible: root.secret
        theme: root.theme
        selected: root.revealSelected
        text: root.translator.text(root.revealed ? "action.hide" : "action.show")
        onRequested: {
            root.toggleReveal()
            input.forceActiveFocus()
        }
    }
}
