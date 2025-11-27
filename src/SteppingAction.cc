//
// ********************************************************************
// * License and Disclaimer                                           *
// *                                                                  *
// * The  Geant4 software  is  copyright of the Copyright Holders  of *
// * the Geant4 Collaboration.  It is provided  under  the terms  and *
// * conditions of the Geant4 Software License,  included in the file *
// * LICENSE and available at  http://cern.ch/geant4/license .  These *
// * include a list of copyright holders.                             *
// *                                                                  *
// * Neither the authors of this software system, nor their employing *
// * institutes,nor the agencies providing financial support for this *
// * work  make  any representation or  warranty, express or implied, *
// * regarding  this  software system or assume any liability for its *
// * use.  Please see the license in the file  LICENSE  and URL above *
// * for the full disclaimer and the limitation of liability.         *
// *                                                                  *
// * This  code  implementation is the result of  the  scientific and *
// * technical work of the GEANT4 collaboration.                      *
// * By using,  copying,  modifying or  distributing the software (or *
// * any work based  on the software)  you  agree  to acknowledge its *
// * use  in  resulting  scientific  publications,  and indicate your *
// * acceptance of all terms of the Geant4 Software license.          *
// ********************************************************************
//
/// \file SteppingAction.cc
/// \brief Implementation of the SteppingAction class
//
// 
//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......
//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

#include "SteppingAction.hh"
#include "Run.hh"
#include "HistoManager.hh"
//#include "TreeManager.hh"

#include "G4ParticleTypes.hh"
#include "G4RunManager.hh"
#include "G4HadronicProcess.hh"

#include "G4HadronicProcessStore.hh"
#include "G4SystemOfUnits.hh"
#include "G4UnitsTable.hh"

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

SteppingAction::SteppingAction(HistoManager* histo)
  : G4UserSteppingAction(),
    fHistoManager(histo)
{ 
ExcitationE = 0.;
xs1=0;
xs2=0;
}

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

SteppingAction::~SteppingAction()
{ }

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

void SteppingAction::UserSteppingAction(const G4Step* aStep)
{
 Run* run 
   = static_cast<Run*>(G4RunManager::GetRunManager()->GetNonConstCurrentRun());
         
  // count processes
  // 
  const G4StepPoint* endPoint = aStep->GetPostStepPoint();
  G4VProcess* process = const_cast<G4VProcess*>(endPoint->GetProcessDefinedStep());                 
  run->CountProcesses(process);
  G4HadronicProcessStore* store = G4HadronicProcessStore::Instance();
  G4Material* material = aStep->GetPostStepPoint()->GetMaterial();
  const G4Element* element = material->GetElement(0);
  G4ParticleDefinition* particle = aStep->GetTrack()->GetDefinition();
  G4double Ekin = aStep->GetTrack()->GetKineticEnergy();
  xs1 = store->GetCrossSectionPerVolume(particle,Ekin,process,material);
  xs2 = store->GetCrossSectionPerAtom(particle,Ekin,process,element,material);

  // G4cout<<"number of elements: "<<material->GetNumberOfElements()<<G4endl;
  // G4cout<<"Process: "<<process->GetProcessName()<<" xs: "<<xs2/CLHEP::millibarn<<G4endl;
  // G4cout<<G4BestUnit(xs2, "Surface")<<G4endl;
  
  // check that an real interaction occured (eg. not a transportation)
  G4StepStatus stepStatus = endPoint->GetStepStatus();
  G4bool transmit = (stepStatus==fGeomBoundary || stepStatus==fWorldBoundary);
  if (transmit) return;
                      
  //real processes : sum track length
  //
  G4double stepLength = aStep->GetStepLength();
  run->SumTrack(stepLength);
  
  //energy-momentum balance initialisation
  //
  const G4StepPoint* prePoint = aStep->GetPreStepPoint();
  G4double Q             = - prePoint->GetKineticEnergy();
  G4ThreeVector Pbalance = - prePoint->GetMomentum();
  
  //initialisation of the nuclear channel identification
  //
  G4String partName = particle->GetParticleName();
  G4String nuclearChannel = partName;
  G4HadronicProcess* hproc = dynamic_cast<G4HadronicProcess*>(process);
  const G4Isotope* target = NULL;
  if (hproc) target = hproc->GetTargetIsotope();
  G4String targetName = "XXXX";  
  if (target) targetName = target->GetName();
  nuclearChannel += " + " + targetName + " --> ";
  if (targetName == "XXXX") run->SetTargetXXX(true);
    
  //scattered primary particle (if any)
  //
  // G4AnalysisManager* analysisManager = G4AnalysisManager::Instance();

  if (aStep->GetTrack()->GetTrackStatus() == fAlive) {
    G4double energy = endPoint->GetKineticEnergy();      
    //
    G4ThreeVector momentum = endPoint->GetMomentum();
    Q        += energy;
    Pbalance += momentum;
    //
    nuclearChannel += partName + " + ";
  }  
  
  //secondaries
  //
  const std::vector<const G4Track*>* secondary 
                                    = aStep->GetSecondaryInCurrentStep();  
  for (size_t lp=0; lp<(*secondary).size(); lp++)
    {
      particle = (*secondary)[lp]->GetDefinition(); 
      G4String name   = particle->GetParticleName();
      G4String type   = particle->GetParticleType();      
      G4double energy = (*secondary)[lp]->GetKineticEnergy();
      G4int A = particle->GetAtomicMass();
      G4int Z =  particle->GetAtomicNumber();
      
      G4ThreeVector momentumDirection = (*secondary)[lp]->GetMomentumDirection();
      
      run->ParticleCount(name,energy);
      
      //atomic mass
      if (type == "nucleus")
	{
	  ExcitationE = ((G4Ions*)particle)->GetExcitationEnergy();
	}
      fHistoManager->FillSecondaries(A, Z,
				     energy/CLHEP::MeV,
				     momentumDirection.theta()/CLHEP::degree);
				       // ExcitationE/CLHEP::eV,
				       // xs1/CLHEP::millibarn);      
      
      //energy-momentum balance
      G4ThreeVector momentum = (*secondary)[lp]->GetMomentum();
      Q        += energy;
      Pbalance += momentum;
      //count e- from internal conversion together with gamma
      if (particle == G4Electron::Electron()) particle = G4Gamma::Gamma();
      //particle flag
      fParticleFlag[particle]++;
    }
  
  //energy-momentum balance
  G4double Pbal = Pbalance.mag();
  run->Balance(Pbal);
  
  // nuclear channel
  const G4int kMax = 16;  
  const G4String conver[] = {"0","","2 ","3 ","4 ","5 ","6 ","7 ","8 ","9 ",
                             "10 ","11 ","12 ","13 ","14 ","15 ","16 "};
  std::map<G4ParticleDefinition*,G4int>::iterator ip;               
  for (ip = fParticleFlag.begin(); ip != fParticleFlag.end(); ip++) {
    particle = ip->first;
    G4String name = particle->GetParticleName();      
    G4int nb = ip->second;
    if (nb > kMax) nb = kMax;   
    G4String Nb = conver[nb];    
    if (particle == G4Gamma::Gamma()) {
     run->CountGamma(nb);
     Nb = "N ";
     name = "gamma or e-";
    } 
    if (ip != fParticleFlag.begin()) nuclearChannel += " + ";
    nuclearChannel += Nb + name;
  }
 
  ///G4cout << "\n nuclear channel: " << nuclearChannel << G4endl;
  run->CountNuclearChannel(nuclearChannel, Q);
    
  fParticleFlag.clear();
              
  // kill event after first interaction
  //
  G4RunManager::GetRunManager()->AbortEvent();  
}

//....oooOO0OOooo........oooOO0OOooo........oooOO0OOooo........oooOO0OOooo......

