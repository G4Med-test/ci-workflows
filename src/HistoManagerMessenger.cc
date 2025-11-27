#include "HistoManagerMessenger.hh"
#include "HistoManagerHelper.hh"
#include "G4UIcmdWithABool.hh"
#include "G4UIcmdWithAnInteger.hh"
#include "G4UIcmdWithAString.hh"
#include "G4UIdirectory.hh"

HistoManagerMessenger::HistoManagerMessenger(HistoManagerHelper* aHistoManager)
  : histoManager(aHistoManager)
{
  G4cout<<"HistoManagerMessenger::HistoManagerMessenger"<<G4endl;
  histoManagerDir = new G4UIdirectory("/histoManager/");
  selectFileName = new G4UIcmdWithAString("/histoManager/setFileName",this);
  selectFileName->SetParameterName("setFileName",false);
  selectFileName->SetToBeBroadcasted(false);
}

HistoManagerMessenger::~HistoManagerMessenger()
{
  delete selectFileName;
  delete histoManagerDir;
}

void HistoManagerMessenger::SetNewValue(G4UIcommand* command,G4String newValue)
{
  if (command == selectFileName )
    {
      G4cout<<"HistoManagerMessenger: setting output filename "<<newValue<<G4endl;
      histoManager->SetOutputFilename(newValue);
      // HistoManager::Instance()->PhysicsList = newValue;
    } 
  else
    {
      G4cerr << "***** Command is not found !!! " << newValue << G4endl;
    }

}
