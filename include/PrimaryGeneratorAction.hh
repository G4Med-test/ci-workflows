#ifndef PrimaryGeneratorAction_h
#define PrimaryGeneratorAction_h 1

#include "G4VUserPrimaryGeneratorAction.hh"
#include "G4ParticleGun.hh"

class G4Event;
class G4ParticleDefinition;

class PrimaryGeneratorAction : public G4VUserPrimaryGeneratorAction{
  
public:
  PrimaryGeneratorAction(const G4double position);    
  ~PrimaryGeneratorAction();
  
  virtual void GeneratePrimaries(G4Event*);
  inline G4ParticleDefinition* GetParticleDefinition() {return fParticleGun->GetParticleDefinition();};
  inline G4double GetParticleEnergy() {return fParticleGun->GetParticleEnergy();};

private:
  G4ParticleGun* fParticleGun;
 
};

#endif
