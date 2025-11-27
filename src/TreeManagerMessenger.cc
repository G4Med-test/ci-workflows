#include "TreeManagerMessenger.hh"
#include "TreeManagerHelper.hh"
#include "G4UIcmdWithABool.hh"
#include "G4UIcmdWithAnInteger.hh"
#include "G4UIcmdWithAString.hh"
#include "G4UIdirectory.hh"

TreeManagerMessenger::TreeManagerMessenger(TreeManagerHelper* aTreeManager)
  : treeManager(aTreeManager)
{
  G4cout<<"TreeManagerMessenger::TreeManagerMessenger"<<G4endl;
  treeManagerDir = new G4UIdirectory("/treeManager/");
  selectFileName = new G4UIcmdWithAString("/treeManager/setFileName",this);
  selectFileName->SetParameterName("setFileName",false);
  selectFileName->SetToBeBroadcasted(false);
}

TreeManagerMessenger::~TreeManagerMessenger()
{
  delete selectFileName;
  delete treeManagerDir;
}

void TreeManagerMessenger::SetNewValue(G4UIcommand* command,G4String newValue)
{
  if (command == selectFileName )
    {
      G4cout<<"TreeManagerMessenger: setting output filename "<<newValue<<G4endl;
      treeManager->SetOutputFilename(newValue);
      // TreeManager::Instance()->PhysicsList = newValue;
    } 
  else
    {
      G4cerr << "***** Command is not found !!! " << newValue << G4endl;
    }

}
