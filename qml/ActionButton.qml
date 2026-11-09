import QtQuick 2.15

Rectangle {
    id: root
    property var theme
    property string text: "Action"
    property bool primary: false
    property bool selected: false
    readonly property bool inverted: (primary || (theme.navigationFocus && selected))
                                     !== pressArea.highlighted
    signal requested()

    color: inverted ? theme.ink : theme.paper
    border.color: theme.ink
    border.width: theme.controlBorderWidth
    opacity: enabled ? 1 : 0.45

    Text {
        anchors.centerIn: parent
        width: parent.width - root.theme.compactMargin
        text: root.text
        color: root.inverted ? root.theme.paper : root.theme.ink
        font.family: root.theme.displayFont
        font.pixelSize: root.theme.controlSize
        font.bold: root.primary
        horizontalAlignment: Text.AlignHCenter
        elide: Text.ElideRight
    }

    PressArea {
        id: pressArea
        anchors.fill: parent
        theme: root.theme
        enabled: root.enabled
        onTriggered: root.requested()
    }
}
