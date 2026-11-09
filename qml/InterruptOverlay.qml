import QtQuick 2.15

Item {
    id: root
    objectName: "interruptOverlay"
    property var theme
    property var translator
    property string title: ""
    property string message: ""
    property bool inverted: false
    property bool opaqueBackdrop: false
    property string dismissLabel: ""
    property var choices: []
    property int selectedIndex: 0
    readonly property string activeLanguage: translator
        ? String(translator.language) : "en"
    readonly property bool hasChoices: choices && choices.length >= 2
    readonly property color cardPaper: inverted ? theme.ink : theme.paper
    readonly property color cardInk: inverted ? theme.paper : theme.ink
    readonly property int cardPadding: Math.round(24 * theme.scale)
    signal dismissRequested()
    signal choiceRequested(int index)

    Rectangle {
        anchors.fill: parent
        visible: root.opaqueBackdrop
        color: root.theme.paper
    }

    MouseArea {
        anchors.fill: parent
        onClicked: {
            if (!root.hasChoices) root.dismissRequested()
        }
        onWheel: wheel.accepted = true
    }

    Rectangle {
        id: card
        objectName: "interruptCard"
        anchors.centerIn: parent
        width: Math.min(parent.width - 2 * root.theme.outerMargin, 680 * root.theme.scale)
        height: Math.min(parent.height - 2 * root.theme.outerMargin,
                         cardContents.implicitHeight + 2 * root.cardPadding)
        color: root.cardPaper
        border.color: root.cardInk
        border.width: Math.max(2, root.theme.divider)
        clip: true
        z: 1

        Column {
            id: cardContents
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: root.cardPadding
            spacing: Math.round(14 * root.theme.scale)

            Text {
                width: parent.width
                text: root.title.length > 0 ? root.title : root.message
                color: root.cardInk
                font.family: root.theme.displayFont
                font.pixelSize: root.theme.titleSize
                font.bold: true
                wrapMode: Text.Wrap
                maximumLineCount: 2
                elide: Text.ElideRight
                horizontalAlignment: Text.AlignLeft
            }

            Rectangle {
                width: parent.width
                height: root.theme.divider
                color: root.cardInk
            }

            Text {
                width: parent.width
                visible: root.title.length > 0 && root.message.length > 0
                text: root.message
                color: root.cardInk
                font.family: root.theme.bodyFont
                font.pixelSize: root.theme.dialogBodySize
                wrapMode: Text.Wrap
                lineHeight: 1.15
                maximumLineCount: root.height > root.width ? 12 : 7
                elide: Text.ElideRight
                horizontalAlignment: Text.AlignLeft
            }

            Text {
                visible: !root.hasChoices && root.dismissLabel.length === 0
                width: parent.width
                text: {
                    var language = root.activeLanguage
                    return root.translator
                        ? root.translator.text("interrupt.dismiss_hint")
                        : "Press a key or tap the screen to close this message."
                }
                color: root.cardInk
                font.family: root.theme.bodyFont
                font.pixelSize: root.theme.hintSize
                wrapMode: Text.Wrap
                horizontalAlignment: Text.AlignLeft
            }

            ActionButtonRow {
                visible: root.hasChoices
                width: parent.width
                theme: root.theme
                leftText: root.hasChoices ? String(root.choices[0]) : "Cancel"
                rightText: root.hasChoices ? String(root.choices[1]) : "Continue"
                leftSelected: root.selectedIndex === 0
                rightSelected: root.selectedIndex === 1
                rightPrimary: true
                onLeftRequested: root.choiceRequested(0)
                onRightRequested: root.choiceRequested(1)
            }

            ActionButton {
                visible: !root.hasChoices && root.dismissLabel.length > 0
                width: parent.width
                height: root.theme.rowHeight
                theme: root.theme
                text: root.dismissLabel
                primary: true
                onRequested: root.dismissRequested()
            }
        }
    }
}
