import QtQuick 2.15

Rectangle {
    id: root
    objectName: "menuPage"
    property var theme
    property var translator
    property string title: "Menu"
    property string hint: ""
    property var items: []
    property int selectedIndex: 0
    readonly property string activeLanguage: translator
        ? String(translator.language) : "en"
    signal activated(string itemId)
    signal choiceRequested(string itemId, var value)
    signal selectionRequested(int index)
    signal backRequested()

    // Updating rows in place preserves their delegates across menu changes.
    // Replacing a QVariantList model rebuilds the entire scene on each entry.
    ListModel { id: menuRows; dynamicRoles: true }
    function syncRows() {
        for (var index = 0; index < items.length; index++) {
            var row = {entry: items[index]}
            if (index < menuRows.count) menuRows.set(index, row)
            else menuRows.append(row)
        }
        if (menuRows.count > items.length)
            menuRows.remove(items.length, menuRows.count - items.length)
    }
    onItemsChanged: syncRows()
    Component.onCompleted: syncRows()

    color: theme.paper

    PageHeader {
        id: header
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.leftMargin: root.theme.outerMargin
        anchors.rightMargin: root.theme.outerMargin
        theme: root.theme
        title: root.title
        backVisible: true
        onBackRequested: root.backRequested()
    }

    ListView {
        id: list
        objectName: "menuList"
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: header.bottom
        anchors.bottom: pageHint.visible ? pageHint.top : parent.bottom
        anchors.leftMargin: root.theme.outerMargin
        anchors.rightMargin: root.theme.outerMargin
        anchors.topMargin: root.theme.compactMargin
        anchors.bottomMargin: root.theme.compactMargin
        clip: true
        interactive: true
        boundsBehavior: Flickable.StopAtBounds
        highlightFollowsCurrentItem: false
        highlightMoveDuration: 0
        highlightResizeDuration: 0
        model: menuRows
        currentIndex: root.theme.navigationFocus ? root.selectedIndex : -1
        onCurrentIndexChanged: {
            if (currentIndex >= 0)
                positionViewAtIndex(currentIndex, ListView.Contain)
        }

        delegate: Rectangle {
            id: menuRow
            width: list.width
            property int rowIndex: index
            property var itemData: model.entry
            property string itemKind: String(itemData.kind || "action")
            property bool selectable: itemKind !== "info"
            property bool selected: selectable && (rowPress.highlighted
                || (root.theme.navigationFocus && index === root.selectedIndex))
            property bool stackedChoice: itemKind === "choice"
                                         && width < Math.round(700 * root.theme.scale)
            color: selected ? root.theme.selectedPaper : root.theme.paper
            height: stackedChoice
                    ? Math.max(root.theme.rowHeight, Math.round(104 * root.theme.scale))
                    : Math.max(root.theme.rowHeight,
                               rowText.implicitHeight + root.theme.compactMargin)

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: 1
                color: root.theme.ink
            }

            Column {
                id: rowText
                anchors.left: parent.left
                anchors.right: trailing.left
                anchors.leftMargin: root.theme.compactMargin
                anchors.rightMargin: root.theme.compactMargin
                anchors.verticalCenter: parent.verticalCenter
                spacing: Math.round(2 * root.theme.scale)
                visible: menuRow.itemKind !== "choice"

                Text {
                    width: parent.width
                    text: menuRow.itemData.label || ""
                    color: menuRow.selected ? root.theme.selectedInk : root.theme.ink
                    font.family: root.theme.displayFont
                    font.pixelSize: root.theme.bodySize
                    elide: Text.ElideRight
                }

                Text {
                    width: parent.width
                    visible: menuRow.itemKind !== "toggle"
                             && (menuRow.itemData.detail || "").length > 0
                    text: menuRow.itemData.detail || ""
                    color: menuRow.selected ? root.theme.selectedInk : root.theme.ink
                    font.family: root.theme.bodyFont
                    font.pixelSize: root.theme.detailSize
                    wrapMode: Text.Wrap
                    maximumLineCount: 2
                    elide: Text.ElideRight
                }
            }

            Item {
                id: trailing
                anchors.right: parent.right
                anchors.rightMargin: root.theme.compactMargin
                anchors.verticalCenter: parent.verticalCenter
                width: menuRow.itemKind === "info"
                       ? 0 : Math.round(54 * root.theme.scale)
                height: Math.round(30 * root.theme.scale)
                visible: menuRow.itemKind !== "choice"
                         && menuRow.itemKind !== "info"

                Text {
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    visible: menuRow.itemKind === "submenu"
                             || menuRow.itemKind === "text"
                             || menuRow.itemKind === "number"
                    text: "›"
                    color: menuRow.selected ? root.theme.selectedInk : root.theme.ink
                    font.family: root.theme.displayFont
                    font.pixelSize: root.theme.bodySize
                    font.bold: true
                }

                ToggleSwitch {
                    visible: menuRow.itemKind === "toggle"
                    anchors.centerIn: parent
                    theme: root.theme
                    checked: Boolean(menuRow.itemData.checked)
                    inverted: menuRow.selected
                }
            }

            Text {
                id: choiceLabel
                anchors.left: parent.left
                anchors.leftMargin: root.theme.compactMargin
                anchors.top: menuRow.stackedChoice ? parent.top : undefined
                anchors.topMargin: menuRow.stackedChoice
                                   ? Math.round(8 * root.theme.scale)
                                   : 0
                anchors.verticalCenter: menuRow.stackedChoice
                                        ? undefined
                                        : parent.verticalCenter
                width: menuRow.stackedChoice
                       ? parent.width - root.theme.compactMargin * 2
                       : Math.min(Math.round(240 * root.theme.scale), parent.width * 0.30)
                visible: menuRow.itemKind === "choice"
                text: menuRow.itemData.label || ""
                color: menuRow.selected ? root.theme.selectedInk : root.theme.ink
                font.family: root.theme.displayFont
                font.pixelSize: root.theme.bodySize
                elide: Text.ElideRight
            }

            Row {
                id: choiceOptions
                anchors.left: menuRow.stackedChoice ? parent.left : choiceLabel.right
                anchors.right: parent.right
                anchors.leftMargin: root.theme.compactMargin
                anchors.rightMargin: root.theme.compactMargin
                anchors.bottom: menuRow.stackedChoice ? parent.bottom : undefined
                anchors.bottomMargin: menuRow.stackedChoice
                                      ? Math.round(8 * root.theme.scale)
                                      : 0
                anchors.verticalCenter: menuRow.stackedChoice
                                        ? undefined
                                        : parent.verticalCenter
                height: Math.round(42 * root.theme.scale)
                visible: menuRow.itemKind === "choice"
                z: 2

                Repeater {
                    id: choiceRepeater
                    model: menuRow.itemData.choices || []

                    delegate: Rectangle {
                        id: choiceOption
                        width: choiceOptions.width / Math.max(1, choiceRepeater.count)
                        height: choiceOptions.height
                        readonly property bool inverted: menuRow.selected || choicePress.highlighted
                        color: inverted ? root.theme.selectedPaper : root.theme.paper

                        RadioIndicator {
                            id: choiceRadio
                            anchors.left: parent.left
                            anchors.verticalCenter: parent.verticalCenter
                            theme: root.theme
                            checked: Boolean(modelData.selected)
                            inverted: choiceOption.inverted
                        }

                        Text {
                            anchors.left: choiceRadio.right
                            anchors.right: parent.right
                            anchors.leftMargin: Math.round(6 * root.theme.scale)
                            anchors.rightMargin: Math.round(4 * root.theme.scale)
                            anchors.verticalCenter: parent.verticalCenter
                            text: String(modelData.shortLabel || modelData.label || "")
                            color: choiceOption.inverted ? root.theme.selectedInk : root.theme.ink
                            font.family: root.theme.bodyFont
                            font.pixelSize: root.theme.controlSize
                            elide: Text.ElideRight
                        }

                        PressArea {
                            id: choicePress
                            anchors.fill: parent
                            theme: root.theme
                            actionData: ({row: menuRow.rowIndex,
                                          itemId: String(menuRow.itemData.id),
                                          value: modelData.value})
                            onTriggered: function(data) {
                                root.selectionRequested(data.row)
                                root.choiceRequested(data.itemId, data.value)
                            }
                        }
                    }
                }
            }

            PressArea {
                id: rowPress
                anchors.fill: parent
                theme: root.theme
                enabled: menuRow.selectable && menuRow.itemKind !== "choice"
                actionData: ({row: menuRow.rowIndex, itemId: String(menuRow.itemData.id)})
                onTriggered: function(data) {
                    root.selectionRequested(data.row)
                    root.activated(data.itemId)
                }
            }
        }
    }

    PageHint {
        id: pageHint
        theme: root.theme
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: root.theme.outerMargin
        visible: root.hint.length > 0
        text: root.hint
    }

}
