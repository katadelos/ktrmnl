import QtQuick 2.15

Row {
    id: root
    property var theme
    property string leftText: "Cancel"
    property string rightText: "Save"
    property bool leftSelected: false
    property bool rightSelected: false
    property bool rightPrimary: true
    property bool leftEnabled: true
    property bool rightEnabled: true
    signal leftRequested()
    signal rightRequested()

    spacing: theme.compactMargin
    height: theme.rowHeight

    ActionButton {
        width: Math.floor((root.width - root.spacing) / 2)
        height: root.height
        theme: root.theme
        text: root.leftText
        selected: root.leftSelected
        enabled: root.leftEnabled
        onRequested: root.leftRequested()
    }

    ActionButton {
        width: root.width - root.spacing - Math.floor((root.width - root.spacing) / 2)
        height: root.height
        theme: root.theme
        text: root.rightText
        // Keep the ordinary right-hand action primary, but let an explicit
        // left selection be the only filled button in confirmation rows.
        primary: root.rightPrimary && (!root.theme.navigationFocus
                                      || !root.leftSelected || root.rightSelected)
        selected: root.rightSelected
        enabled: root.rightEnabled
        onRequested: root.rightRequested()
    }
}
